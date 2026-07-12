# Batch tool-lock validation probe

This local probe checks whether `run_batch()` can reach pending task execution
without first calling `validate_repo_tool_lock()`. It reads source files from a
KCS checkout only. It does not run KCS commands, invoke adapters, use
credentials, mutate `.kcs`, or contact any service.

Run against the vulnerable revision:

```sh
cd poc
KCS_REPO=../kcs make run
```

Run against a patched tree:

```sh
cd poc
KCS_REPO=../kcs EXPECT=fixed make run
```
