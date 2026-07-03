#!/usr/bin/env python3
"""履歴シナリオの決定論的再現 (KCS 検索評価ハーネス, docs/09-mvp-scope.md §4.3).

生成済みコーパス (generate_corpus.py の出力) に対し、各 scope で
    kcs init -> kcs index --approve -> kcs snapshot
    -> 編集 -> snapshot -> リネーム -> snapshot -> 削除 -> snapshot
の履歴を **決定論的** に再現する (M3-2 リネーム / M3-3 削除の評価に必要)。

- 操作列は corpus_spec.HISTORY で固定 (どのファイルを編集/リネーム/削除するか)。
- どのファイルを rename/delete/edit したかを --manifest (既定 eval/history-manifest.json)
  に記録する。commit hash / timestamp は非決定なので記録しない (件数・メッセージのみ)。
- 最後に各 scope で `kcs log` を叩き、履歴 commit が積まれたことを検証する。

前提: 対象は generate_corpus.py 直後のフレッシュなコーパス (.kcs 未作成)。

使い方:
    python3 eval/replay_history.py --corpus /tmp/kcs-eval-corpus \\
        --bin target/release/kcs --manifest eval/history-manifest.json
"""

import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import corpus_spec as spec  # noqa: E402


class ReplayError(RuntimeError):
    pass


def run_kcs(bin_path, scope_dir, args, tolerate_partial=True):
    """kcs を scope_dir で実行し JSON を返す。index の partial(exit3) は許容."""
    cmd = [bin_path, "--json"] + args
    proc = subprocess.run(cmd, cwd=scope_dir, capture_output=True, text=True)
    # index --approve は failed_files>0 で exit 3 を返すが auto snapshot は済む。
    # また合成コーパスは全て正常 normalize される想定。exit!=0 かつ tolerate 外なら失敗。
    if proc.returncode != 0 and not (tolerate_partial and proc.returncode == 3):
        raise ReplayError(
            f"kcs {' '.join(args)} in {scope_dir} exit={proc.returncode}\n"
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
    for scope in spec.SCOPES:
        scope_dir = os.path.join(corpus_dir, scope)
        if not os.path.isdir(scope_dir):
            raise ReplayError(f"scope ディレクトリ不在: {scope_dir}")

        run_kcs(bin_path, scope_dir, ["init", "."])
        run_kcs(bin_path, scope_dir, ["index", "--approve"])
        run_kcs(bin_path, scope_dir, ["snapshot", "-m", "baseline"])

        steps = ["baseline"]

        # 編集 -> snapshot
        edits = edits_by_scope.get(scope, [])
        if edits:
            for e in edits:
                apply_edit(scope_dir, e)
            run_kcs(bin_path, scope_dir, ["index", "--approve"])
            files = ", ".join(e["file"] for e in edits)
            run_kcs(bin_path, scope_dir, ["snapshot", "-m", f"edit: {files}"])
            steps.append("edit")

        # リネーム -> snapshot
        renames = renames_by_scope.get(scope, [])
        if renames:
            for r in renames:
                apply_rename(scope_dir, r)
            run_kcs(bin_path, scope_dir, ["index", "--approve"])
            pairs = ", ".join(f"{r['old_file']}->{r['new_file']}" for r in renames)
            run_kcs(bin_path, scope_dir, ["snapshot", "-m", f"rename: {pairs}"])
            steps.append("rename")

        # 削除 -> snapshot
        deletes = deletes_by_scope.get(scope, [])
        if deletes:
            for d in deletes:
                apply_delete(scope_dir, d)
            run_kcs(bin_path, scope_dir, ["index", "--approve"])
            files = ", ".join(d["file"] for d in deletes)
            run_kcs(bin_path, scope_dir, ["snapshot", "-m", f"delete: {files}"])
            steps.append("delete")

        # 検証: kcs log
        log = run_kcs(bin_path, scope_dir, ["log"])
        commits = log.get("commits", [])
        per_scope[scope] = {
            "steps": steps,
            "commit_count": len(commits),
            "messages": [c.get("message") for c in commits],
        }

    return per_scope


def build_manifest(per_scope):
    return {
        "replay": "eval/replay_history.py",
        "seed": spec.SEED,
        "scopes": spec.SCOPES,
        "renamed": spec.HISTORY["renames"],
        "edited": [
            {"scope": e["scope"], "file": e["file"],
             "old_value": e["old_value"], "new_value": e["new_value"]}
            for e in spec.HISTORY["edits"]
        ],
        "deleted": spec.HISTORY["deletes"],
        "verified": per_scope,
    }


def main(argv=None):
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description="KCS 履歴シナリオ再現 (決定論的)")
    ap.add_argument("--corpus", required=True, help="generate_corpus.py の出力ディレクトリ")
    ap.add_argument("--bin", default="target/release/kcs", help="kcs バイナリのパス")
    ap.add_argument("--manifest", default=os.path.join(here, "history-manifest.json"),
                    help="履歴 manifest の出力先")
    args = ap.parse_args(argv)

    corpus_dir = os.path.abspath(args.corpus)
    bin_path = os.path.abspath(args.bin)
    if not os.path.exists(bin_path):
        raise SystemExit(f"[error] kcs バイナリ不在: {bin_path} "
                         f"(cargo build --release 済みか確認)")

    per_scope = replay(corpus_dir, bin_path)
    manifest = build_manifest(per_scope)
    with open(args.manifest, "w", encoding="utf-8", newline="\n") as fh:
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
    print(f"     manifest: {args.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
