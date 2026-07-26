#!/usr/bin/env python3
"""Build the indexed fixture environments `run_baseline.py` / `run_qhard.py` search.

Those two runners are the only instrument that can detect a search-quality
regression: the synthetic `run_eval.py` scores 1.0/1.0/1.0 against a 0.8 target,
i.e. it sits at its ceiling and cannot measure degradation. The 24-query
fixture-B set last measured 0.9167 with hard3 at 6/8, so it has the headroom the
synthetic set does not. Both runners resolve `<fixture-root>/env/<name>/xdg-*`
and neither builds it — this is the missing half, and it was never committed
(`git log --diff-filter=D` finds no deletion; it simply never existed in the
repo).

## What a fixture is

    <fixture-root>/
      <persona>/home/...            a WORKING COPY of the corpus, with .kio dirs
      env/<persona>/xdg-{config,data,cache}
      env/qhard/xdg-{config,data,cache}
      registration-report.json

The source corpus is **never touched**. `run_baseline.py` compares Kio against
mdfind and rga on a PRISTINE copy — baselines must not see Kio-derived
artifacts — so the tree that gets `.kio` directories has to be a copy, and the
one the baselines read stays clean.

## Which directories become scopes

Every directory under `<persona>/home` that DIRECTLY contains at least one file.
Not a rule invented here: it reproduces the surviving fixture exactly (20 leaves
for each of p01..p20, matching both `scope-registry.sqlite` and the recorded
`registration-report.json`).

## Cost, and why `--offline` is not a cheap substitute

`--online` spends real money — the recorded run was $1.07 across 1,112 ledger
rows for OCR alone, with embedding on top. Hence `--resume` (default): a run
that dies halfway must not make you pay for the finished scopes again.

There is no free version of this measurement. Of the 24 frozen fixture-B
answers, 4 are carried by `.md` and the other 20 by `.pdf` / `.docx` / `.pptx`
/ `.png` / `.jpeg`, all of which route through the OCR lane
(`tasks/q-hard-20persona-phase1-requirements-v2.md` §1). An `--offline` fixture
therefore tops out at 4/24 = 0.167 against a 0.8 gate: it proves the scopes
register and the runner can search them, and it measures no search quality at
all.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent


def scope_leaves(home: Path) -> list[Path]:
    """Directories directly holding >= 1 file, in a stable order."""
    return sorted(
        path
        for path in home.rglob("*")
        if path.is_dir()
        and path.name != ".kio"
        and ".kio" not in path.parts
        and any(child.is_file() for child in path.iterdir())
    )


def hermetic_env(fixture_root: Path, env_name: str) -> dict[str, str]:
    """The child environment for one persona.

    Every `KIO_TEST_*` is stripped, and that is not hygiene — it is the
    difference between a fixture and a lie. A stray `KIO_TEST_GEMINI_EMBED=mock`
    would fill this store with mock vectors, and the baseline measured against it
    would be a number about the mock. The runners strip the same set when they
    search; the fixture has to be built under the same rule.
    """
    base = fixture_root / "env" / env_name
    env = {k: v for k, v in os.environ.items() if not k.startswith("KIO_TEST_")}
    env["XDG_CONFIG_HOME"] = str(base / "xdg-config")
    env["XDG_DATA_HOME"] = str(base / "xdg-data")
    env["XDG_CACHE_HOME"] = str(base / "xdg-cache")
    for name in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME"):
        Path(env[name]).mkdir(parents=True, exist_ok=True)
    return env


def run_kio(
    binary: Path, args: list[str], cwd: Path, env: dict[str, str], timeout: float
) -> tuple[int, Any]:
    try:
        completed = subprocess.run(
            [str(binary), *args, "--json"],
            cwd=str(cwd),
            env=env,
            capture_output=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return 124, {"error": f"timed out after {timeout}s"}
    stream = completed.stdout or completed.stderr
    try:
        return completed.returncode, json.loads(stream)
    except (json.JSONDecodeError, ValueError):
        return completed.returncode, {"raw": stream.decode("utf-8", "replace")[:600]}


def register_scope(
    binary: Path,
    scope: Path,
    env: dict[str, str],
    online: bool,
    realtime: bool,
    timeout: float,
) -> dict[str, Any] | None:
    """`init` + `index` one scope. Returns None on success, else a failure record."""
    if not (scope / ".kio").is_dir():
        code, body = run_kio(binary, ["init"], scope, env, timeout)
        if code != 0:
            return {"scope": str(scope), "step": "init", "exit": code, "body": body}

    if online:
        index_args = ["index", "--approve", "--yes"]
        if realtime:
            index_args.append("--realtime")
    else:
        index_args = ["index", "--offline", "--yes"]
    code, body = run_kio(binary, index_args, scope, env, timeout)
    # Exit 3 is documented partial success (06 §7); the scope IS indexed and the
    # runners can search it. Anything else is a real failure.
    if code not in (0, 3):
        return {"scope": str(scope), "step": "index", "exit": code, "body": body}
    return None


def pending_tasks(binary: Path, scope: Path, env: dict[str, str], timeout: float) -> int:
    """How many enrichment tasks this scope is still waiting on."""
    code, body = run_kio(binary, ["status"], scope, env, timeout)
    if code != 0 or not isinstance(body, dict):
        return -1
    return sum(
        1 for task in body.get("tasks", []) if task.get("status") not in ("done", "partial")
    )


def drain_scope(
    binary: Path, scope: Path, env: dict[str, str], rounds: int, interval: float, timeout: float
) -> int:
    """Collect Batch results until the scope stops making progress.

    Without `--realtime`, `index` does not finish the online work — it hands the
    OCR and embedding off to the provider's Batch lane, which 07 §5.3 allows up
    to a 24h turnaround. So indexing alone leaves a fixture that has been PAID
    for and cannot answer anything: the answers sit behind tasks nobody
    collected. This is the collection.

    Stops when a round changes nothing rather than when the count hits zero, so
    a job the provider has not finished yet ends the loop instead of spinning
    for hours. Whatever remains is reported, and re-running the script drains it
    (already-indexed scopes are skipped, so no send is repeated).
    """
    remaining = pending_tasks(binary, scope, env, timeout)
    for _ in range(rounds):
        if remaining <= 0:
            break
        run_kio(binary, ["batch", "resume", "--online"], scope, env, timeout)
        now = pending_tasks(binary, scope, env, timeout)
        if now < 0 or now >= remaining:
            remaining = now
            break
        remaining = now
        if remaining > 0 and interval > 0:
            time.sleep(interval)
    return remaining


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--corpus",
        type=Path,
        required=True,
        help="pristine source tree holding <persona>/home/... — never modified",
    )
    parser.add_argument("--out", type=Path, required=True, help="fixture root to build")
    parser.add_argument("--bin", type=Path, required=True, help="the kio binary")
    parser.add_argument(
        "--personas",
        default="",
        help="comma-separated subset (default: every <corpus>/p* with a home/)",
    )
    parser.add_argument(
        "--env-name",
        default="",
        help="register every persona into ONE env under this name, as the qhard "
        "pack does (default: one env per persona)",
    )
    parser.add_argument(
        "--online",
        action="store_true",
        help="run the OCR + embedding lanes. SPENDS MONEY (~$1.07 recorded for "
        "20 personas, OCR only; embedding is extra). Effectively REQUIRED for a "
        "usable baseline — see the note this prints without it.",
    )
    parser.add_argument(
        "--realtime",
        action="store_true",
        help="online only: take the realtime lane instead of Batch. Finishes "
        "within the run rather than waiting on a turnaround of up to 24h, at "
        "DOUBLE the unit price (07 §5.3).",
    )
    parser.add_argument(
        "--drain-rounds",
        type=int,
        default=12,
        help="online+Batch only: how many `batch resume` passes per scope before "
        "leaving the rest pending (default 12)",
    )
    parser.add_argument(
        "--drain-interval", type=float, default=20.0, help="seconds between drain passes"
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="re-copy and re-index scopes that are already built (re-pays OCR)",
    )
    parser.add_argument("--timeout", type=float, default=900.0)
    args = parser.parse_args()

    # Absolute, because every `kio` call runs with `cwd` set to the scope it is
    # indexing — a relative `--bin` or `--out` would resolve against that scope.
    args.corpus = args.corpus.resolve()
    args.out = args.out.resolve()
    args.bin = args.bin.resolve()

    if not args.corpus.is_dir():
        print(f"corpus not a directory: {args.corpus}", file=sys.stderr)
        return 2
    if not args.bin.is_file():
        print(f"kio binary not found: {args.bin}", file=sys.stderr)
        return 2

    personas = (
        [p.strip() for p in args.personas.split(",") if p.strip()]
        if args.personas
        else sorted(
            path.name
            for path in args.corpus.iterdir()
            if path.is_dir() and (path / "home").is_dir()
        )
    )
    if not personas:
        print(f"no <persona>/home/ found under {args.corpus}", file=sys.stderr)
        return 2

    args.out.mkdir(parents=True, exist_ok=True)
    started = time.time()
    results: list[dict[str, Any]] = []

    for persona in personas:
        source_home = args.corpus / persona / "home"
        if not source_home.is_dir():
            results.append({"persona": persona, "error": "no home/ in corpus"})
            continue

        work_home = args.out / persona / "home"
        if work_home.exists() and args.no_resume:
            shutil.rmtree(args.out / persona)
        if not work_home.exists():
            work_home.parent.mkdir(parents=True, exist_ok=True)
            # `.kio` is excluded so a fixture root handed back as --corpus by
            # mistake cannot smuggle a previous run's store into a fresh one.
            shutil.copytree(
                source_home, work_home, ignore=shutil.ignore_patterns(".kio")
            )

        env = hermetic_env(args.out, args.env_name or persona)
        leaves = scope_leaves(work_home)
        failures: list[dict[str, Any]] = []
        indexed_ok = 0
        for scope in leaves:
            failure = register_scope(
                args.bin, scope, env, args.online, args.realtime, args.timeout
            )
            if failure is None:
                indexed_ok += 1
            else:
                failures.append(failure)

        # Batch hands the work to the provider and returns; without collecting
        # it the fixture is paid for and still cannot answer.
        still_pending = 0
        if args.online and not args.realtime:
            for scope in leaves:
                remaining = drain_scope(
                    args.bin,
                    scope,
                    env,
                    args.drain_rounds,
                    args.drain_interval,
                    args.timeout,
                )
                still_pending += max(remaining, 0)

        results.append(
            {
                "persona": persona,
                "leaves": len(leaves),
                "indexed_ok": indexed_ok,
                "pending_after_drain": still_pending,
                "failures": failures,
            }
        )
        # Flushed, because this is the only progress signal on a run that takes
        # an hour and spends money — redirected to a file it would otherwise sit
        # in a buffer until the very end, which is exactly when it is useless.
        print(
            f"[{persona}] {indexed_ok}/{len(leaves)} scopes"
            + (f"  ({len(failures)} failed)" if failures else "")
            + (f"  [{still_pending} tasks still pending]" if still_pending else ""),
            flush=True,
        )

    report = {
        "corpus": str(args.corpus),
        "fixture_root": str(args.out),
        "online_expected": args.online,
        "env_name": args.env_name or None,
        "elapsed_s": round(time.time() - started, 1),
        "results": results,
    }
    (args.out / "registration-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    total = sum(r.get("leaves", 0) for r in results)
    ok = sum(r.get("indexed_ok", 0) for r in results)
    pending = sum(r.get("pending_after_drain", 0) for r in results)
    print(f"\n{ok}/{total} scopes across {len(results)} personas -> {args.out}")
    if pending:
        print(
            f"  {pending} enrichment tasks are still pending at the provider.\n"
            "  Re-run this exact command to collect them — indexed scopes are\n"
            "  skipped, so nothing is sent or paid for twice."
        )
    if not args.online:
        print(
            "\n  NOTE: built --offline. This is a PLUMBING CHECK, not a baseline.\n"
            "  Of the 24 frozen fixture-B answers, 4 are carried by .md and the\n"
            "  other 20 by .pdf/.docx/.pptx/.png/.jpeg — every one of which routes\n"
            "  through the OCR lane. So the highest recall an offline fixture can\n"
            "  reach is 4/24 = 0.167 against a 0.8 gate, and a low number here says\n"
            "  nothing about search quality. Use --online to measure."
        )
    return 0 if ok == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
