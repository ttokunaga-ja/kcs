# Batch / Task Research Notes

> Status: integrated
> Canonical refs: [../04-pipeline.md](../04-pipeline.md), [../06-cli-spec.md](../06-cli-spec.md), [../10-operations.md](../10-operations.md)

---

# 結論

Prepare、Markdownize、Embedding、Summary、Classification、Rerank、Index 更新は task として管理する。

task state は正本ではない。失われても object store、tool profile、manifest から未完了作業を再検出できる。

# task model

```text
fields:
  task_id
  task_type
  mode
  input_hash
  tool_profile_hash
  state
  attempts
  next_run_at
  error_code
  fallback_reason
```

`markdownize` task は `mode=full | incremental` を持つ。incremental 不可時は full task を生成する。

# state

```text
pending
running
done
failed_retryable
failed_permanent
cancelled
```

`running` のまま落ちた task は lease timeout で再実行可能に戻す。

# CLI

```bash
kcs status
kcs resume
kcs retry --failed
kcs queue
kcs queue rebuild
```

`queue rebuild` は manifest / objects / runs / index を照合して不足 task を再生成する。

# retry / budget

```text
retry:
  retryable error は backoff して再試行。
  permanent error は人間の対応待ち。

budget:
  API cost、token、file count、elapsed time に cap を設定できる。
  cap 超過時は新規 task を止め、既存 running の終了を待つ。

kill switch:
  すべての online adapter task を停止できる。
```

# idempotency

同じ `(task_type, input_hash, tool_profile_hash, mode)` の done artifact があれば再実行しない。出力の存在確認に失敗した場合のみ `missing_output` として再生成候補にする。

# 正本へ移した内容

```text
task schema / retry / budget      → 04-pipeline.md
CLI                               → 06-cli-spec.md
error / exit code                 → 10-operations.md
```
