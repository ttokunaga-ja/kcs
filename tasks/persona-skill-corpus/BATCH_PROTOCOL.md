# Batch production protocol

## Authority and paths

Generate and validate plan, schedule, render, materialization, and workspace
only through `kio-eval persona`; start with `kio-eval persona plan`. The accepted Rust plan is the sole authority
for the persona ID, Rust `scope_id`, its distinct `scope_path`, and all file
allocation. The final-output directory is exactly:

```text
<workspace-root>/people/<persona-id>-<role>/home/<scope-path>/
```

Never use a home path as a lease identifier and never derive an ID from it. The
Rust lease interface takes `--scope-id <Rust scope id>` and derives all
workspace-owner binding itself; it accepts no caller-supplied record digest.

## Batch lifecycle

1. The parent reads the accepted plan row and chooses one persona and one
   unleased Rust scope ID. It preserves the plan's required home path and
   allocation; this protocol adds no semantic allocation or manifest.
2. The parent obtains one persona coordination lease:

   ```bash
   kio-eval persona lease claim \
     --root <workspace-root> --persona p01 \
     --session <parent-session>
   ```

3. Immediately before assigning a worker, the parent claims the exact Rust
   scope ID. The returned token remains with the parent.

   ```bash
   kio-eval persona lease scope claim \
     --root <workspace-root> --persona p01 --scope-id <rust-scope-id> \
     --parent-session <parent-session> --worker-session <worker-session>
   ```

4. The worker produces a bounded batch of 5–20 planned artifacts and writes
   final artifacts only below the plan row's `home/<scope-path>/`. It does not
   write `_control/`, alter Rust records, change the allocation, or receive a
   release token. Route DOCX/XLSX/PPTX/PDF/image creation through the matching
   skill and inspect the final artifact before reporting it.
5. The parent validates the work against the plan row, records any operational
   checkpoint in its own process, then releases the scope using its Rust scope
   ID and returned token:

   ```bash
   kio-eval persona lease scope release \
     --root <workspace-root> --persona p01 --scope-id <rust-scope-id> \
     --parent-session <parent-session> --release-token <scope-release-token>
   ```

6. Release the parent lease only after all child scope leases are absent:
   `kio-eval persona lease release --root <workspace-root> --persona p01
   --release-token <parent-release-token>`. Interrupted work is inspected with
   `lease show` / `lease scope show`. `lease recover` / `lease scope recover`
   are explicit trusted-coordinator actions after confirmation that the named
   writer stopped. After the lifecycle, `kio-eval persona attest --root
   <materialized-root> --out <new-report>` may publish a create-only bounded
   observation; its Kio/history claims remain false.

Lease state is a duplicate-writer coordination aid, not a privilege boundary
against another process under the same OS account. It is not evidence of Kio
prepare/index/replay, chunks, search correctness, or history readiness.
