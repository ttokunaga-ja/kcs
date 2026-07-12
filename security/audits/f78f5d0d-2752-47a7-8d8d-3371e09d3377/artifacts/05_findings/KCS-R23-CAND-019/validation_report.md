# Validation: status and snapshot read unbounded direct-child files before any cap

- Candidate: `KCS-R23-CAND-019`
- Disposition: **reportable** (`survives: yes`)
- Severity: **medium**
- Confidence: **high (0.98)**
- Method: **V5 exact resource bound + V10 exact trace**

CLI status dispatch opens the repository and calls `Repository::status` at `crates/kcs-cli/src/main.rs:435-442`; status calls `build_working_tree(false)` at `crates/kcs-core/src/scope.rs:306-309`. The shared builder enumerates direct children, skips directories/non-regular/excluded entries, and then unconditionally `fs::read(&path)` into a `Vec<u8>` at `scope.rs:261-295`. `store_raw=false` changes only the post-allocation hash/store branch.

Snapshot's metadata-only preview at `main.rs:452-472` does not enforce a size ceiling. `snapshot_filtered` reaches the same builder with `store_raw=true` at `scope.rs:373-386,413-427`, allocating the whole file and then persisting it. The configured `effective_max_input_bytes` at `main.rs:4425-4444` is applied later only to index adapter processing at `:9047-9061`; it is absent from status/snapshot.

Peak memory is O(largest included direct child), I/O is O(total included bytes), and snapshot additionally copies raw bytes. Existing status/snapshot tests cover only tiny files; max-input tests cover the later index gate. Countercontrols skip subdirectories, working-file symlinks, and explicit exclusions; snapshot holds the store lock; the operator can remove the file. These narrow impact but do not impose a bound before allocation.

Closure: reportable Medium local availability/resource amplification. Enforce metadata/streaming limits before full reads, and define a safe status/snapshot treatment for oversized files.

