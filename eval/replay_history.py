#!/usr/bin/env python3
"""履歴シナリオの決定論的再現 (Kio 検索評価ハーネス, docs/09-mvp-scope.md §4.3).

Rust `kio-eval generate-corpus` が生成したコーパスに対し、各 scope で
    kio init -> kio index --approve -> kio snapshot create
    -> 編集 -> snapshot create -> リネーム -> snapshot create -> 削除 -> snapshot create
の履歴を **決定論的** に再現する (M3-2 リネーム / M3-3 削除の評価に必要)。

- 操作列は corpus_spec.HISTORY で固定 (どのファイルを編集/リネーム/削除するか)。
- どのファイルを rename/delete/edit したかを --manifest (既定 eval/history-manifest.json)
  に記録する。commit hash / timestamp は非決定なので記録しない (件数・メッセージのみ)。
- 最後に各 scope で `kio log` を叩き、履歴 commit が積まれたことを検証する。

前提: 対象は `kio-eval generate-corpus` 直後のフレッシュなコーパス (.kio 未作成)。

使い方:
    python3 eval/replay_history.py --corpus /tmp/kio-eval-corpus \\
        --bin target/release/kio --manifest eval/history-manifest.json
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import corpus_spec as spec  # noqa: E402
from eval_env import subprocess_env  # noqa: E402

# The Kio CLI's JSON protocol is UTF-8.  Spell that out rather than inheriting
# Windows' active console code page through `text=True`.
KIO_SUBPROCESS_TEXT = {"text": True, "encoding": "utf-8", "errors": "strict"}

# anchor の (scope, file) -> 定義 (旧内容の見出し解決に使う)。
# renamed は old_file、edited/deleted は file が anchor の原名と一致する。
_ANCHOR_BY_KEY = {(a["scope"], a["file"]): a for a in spec.ANCHORS}


class ReplayError(RuntimeError):
    pass


def _sha256_file(path):
    """ファイル bytes の sha256 hexdigest (旧内容 raw_hash 解決用)."""
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _sections_for(scope, file_):
    """(scope, file) の anchor 定義から {slug, heading} 列を返す (旧内容の見出し)."""
    anchor = _ANCHOR_BY_KEY.get((scope, file_))
    if not anchor:
        return []
    return [{"slug": s["slug"], "heading": s["heading"]} for s in anchor["sections"]]


def run_kio(bin_path, scope_dir, args, tolerate_partial=True, corpus_dir=None):
    """kio を scope_dir で実行し JSON を返す。index の partial(exit3) は許容."""
    cmd = [bin_path, "--json"] + args
    corpus_dir = corpus_dir or os.path.dirname(scope_dir)
    proc = subprocess.run(
        cmd,
        cwd=scope_dir,
        capture_output=True,
        **KIO_SUBPROCESS_TEXT,
        env=subprocess_env(corpus_dir),
    )
    # index --approve は failed_files>0 で exit 3 を返すが auto snapshot は済む。
    # また合成コーパスは全て正常 normalize される想定。exit!=0 かつ tolerate 外なら失敗。
    if proc.returncode != 0 and not (tolerate_partial and proc.returncode == 3):
        raise ReplayError(
            f"kio {' '.join(args)} in {scope_dir} exit={proc.returncode}\n"
            f"stdout={proc.stdout}\nstderr={proc.stderr}")
    try:
        return json.loads(proc.stdout) if proc.stdout.strip() else {}
    except json.JSONDecodeError:
        return {"_raw": proc.stdout}


def apply_edit(scope_dir, edit):
    path = os.path.join(scope_dir, edit["file"])
    with open(path, "r", encoding="utf-8") as fh:
        content = fh.read()
    if edit["old_value"] not in content:
        raise ReplayError(
            f"edit old_value 不在: {path} :: {edit['old_value']!r}")
    content = content.replace(edit["old_value"], edit["new_value"])
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(content)


def apply_rename(scope_dir, rename):
    src = os.path.join(scope_dir, rename["old_file"])
    dst = os.path.join(scope_dir, rename["new_file"])
    if not os.path.exists(src):
        raise ReplayError(f"rename 元不在: {src}")
    os.rename(src, dst)


def apply_delete(scope_dir, deletion):
    path = os.path.join(scope_dir, deletion["file"])
    if not os.path.exists(path):
        raise ReplayError(f"delete 対象不在: {path}")
    os.remove(path)


def group_by_scope(items):
    out = {}
    for it in items:
        out.setdefault(it["scope"], []).append(it)
    return out


def replay(corpus_dir, bin_path):
    edits_by_scope = group_by_scope(spec.HISTORY["edits"])
    renames_by_scope = group_by_scope(spec.HISTORY["renames"])
    deletes_by_scope = group_by_scope(spec.HISTORY["deletes"])

    per_scope = {}
    # (scope, file/old_file) -> 操作直前 (旧内容) のファイル bytes の sha256。
    # rename は bytes 不変、edit は編集前、delete は削除前を採る。
    old_hashes = {}
    for scope in spec.SCOPES:
        scope_dir = os.path.join(corpus_dir, scope)
        if not os.path.isdir(scope_dir):
            raise ReplayError(f"scope ディレクトリ不在: {scope_dir}")

        run_kio(bin_path, scope_dir, ["init", "."], corpus_dir=corpus_dir)
        run_kio(bin_path, scope_dir, ["index", "--approve"], corpus_dir=corpus_dir)
        run_kio(bin_path, scope_dir, ["snapshot", "create", "-m", "baseline"], corpus_dir=corpus_dir)

        steps = ["baseline"]

        # 編集 -> snapshot (旧値 raw_hash は編集前の bytes)
        edits = edits_by_scope.get(scope, [])
        if edits:
            for e in edits:
                old_hashes[(scope, e["file"])] = _sha256_file(
                    os.path.join(scope_dir, e["file"]))
                apply_edit(scope_dir, e)
            run_kio(bin_path, scope_dir, ["index", "--approve"], corpus_dir=corpus_dir)
            files = ", ".join(e["file"] for e in edits)
            run_kio(bin_path, scope_dir, ["snapshot", "create", "-m", f"edit: {files}"],
                    corpus_dir=corpus_dir)
            steps.append("edit")

        # リネーム -> snapshot (rename は bytes 不変。旧名時点の bytes を記録)
        renames = renames_by_scope.get(scope, [])
        if renames:
            for r in renames:
                old_hashes[(scope, r["old_file"])] = _sha256_file(
                    os.path.join(scope_dir, r["old_file"]))
                apply_rename(scope_dir, r)
            run_kio(bin_path, scope_dir, ["index", "--approve"], corpus_dir=corpus_dir)
            pairs = ", ".join(f"{r['old_file']}->{r['new_file']}" for r in renames)
            run_kio(bin_path, scope_dir, ["snapshot", "create", "-m", f"rename: {pairs}"],
                    corpus_dir=corpus_dir)
            steps.append("rename")

        # 削除 -> snapshot (削除前の bytes を記録)
        deletes = deletes_by_scope.get(scope, [])
        if deletes:
            for d in deletes:
                old_hashes[(scope, d["file"])] = _sha256_file(
                    os.path.join(scope_dir, d["file"]))
                apply_delete(scope_dir, d)
            run_kio(bin_path, scope_dir, ["index", "--approve"], corpus_dir=corpus_dir)
            files = ", ".join(d["file"] for d in deletes)
            run_kio(bin_path, scope_dir, ["snapshot", "create", "-m", f"delete: {files}"],
                    corpus_dir=corpus_dir)
            steps.append("delete")

        # 検証: kio log
        log = run_kio(bin_path, scope_dir, ["log"], corpus_dir=corpus_dir)
        commits = log.get("commits", [])
        per_scope[scope] = {
            "steps": steps,
            "commit_count": len(commits),
            "messages": [c.get("message") for c in commits],
        }

    return per_scope, old_hashes


def build_manifest(per_scope, old_hashes):
    # rename/edit/delete 対象の「旧内容」raw_sha256 と heading を記録する。
    # 評価器の解決層が expected {scope,file,section} -> (raw_hash, section_id) を導くのに使う。
    def _renamed(r):
        return {
            "scope": r["scope"], "old_file": r["old_file"], "new_file": r["new_file"],
            "raw_sha256": old_hashes.get((r["scope"], r["old_file"])),
            "sections": _sections_for(r["scope"], r["old_file"]),
        }

    def _edited(e):
        return {
            "scope": e["scope"], "file": e["file"],
            "old_value": e["old_value"], "new_value": e["new_value"],
            "raw_sha256": old_hashes.get((e["scope"], e["file"])),
            "sections": _sections_for(e["scope"], e["file"]),
        }

    def _deleted(d):
        return {
            "scope": d["scope"], "file": d["file"],
            "raw_sha256": old_hashes.get((d["scope"], d["file"])),
            "sections": _sections_for(d["scope"], d["file"]),
        }

    return {
        "replay": "eval/replay_history.py",
        "seed": spec.SEED,
        "scopes": spec.SCOPES,
        "renamed": [_renamed(r) for r in spec.HISTORY["renames"]],
        "edited": [_edited(e) for e in spec.HISTORY["edits"]],
        "deleted": [_deleted(d) for d in spec.HISTORY["deletes"]],
        "verified": per_scope,
    }


def main(argv=None):
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description="Kio 履歴シナリオ再現 (決定論的)")
    ap.add_argument("--corpus", required=True, help="kio-eval generate-corpus の出力ディレクトリ")
    ap.add_argument("--bin", default="target/release/kio", help="kio バイナリのパス")
    ap.add_argument("--manifest", default=None,
                    help="履歴 manifest の出力先 (既定 <corpus>/history-manifest.json)")
    args = ap.parse_args(argv)

    corpus_dir = os.path.abspath(args.corpus)
    bin_path = os.path.abspath(args.bin)
    if not os.path.exists(bin_path):
        raise SystemExit(f"[error] kio バイナリ不在: {bin_path} "
                         f"(cargo build --release 済みか確認)")

    manifest_path = args.manifest or os.path.join(corpus_dir, "history-manifest.json")
    per_scope, old_hashes = replay(corpus_dir, bin_path)
    manifest = build_manifest(per_scope, old_hashes)
    with open(manifest_path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")

    n_ren = len(manifest["renamed"])
    n_edit = len(manifest["edited"])
    n_del = len(manifest["deleted"])
    total_commits = sum(v["commit_count"] for v in per_scope.values())
    print(f"[ok] 履歴再現完了: {corpus_dir}")
    print(f"     renamed={n_ren} edited={n_edit} deleted={n_del} "
          f"total_commits={total_commits}")
    for scope in spec.SCOPES:
        v = per_scope[scope]
        print(f"       - {scope:12s}: steps={'/'.join(v['steps'])} "
              f"commits={v['commit_count']}")
    print(f"     manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
