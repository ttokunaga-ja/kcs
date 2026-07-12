# Secret-hold terminal-failure revival PoC

This directory contains a local, offline state-machine PoC for the KCS embedding
task bug. It models the `TaskDescriptor` fields changed by the vulnerable
secret-hold and unhold transitions. It does not call an embedding adapter, read
credentials, open sockets, or modify a KCS repository.

Run it from this directory:

```sh
make run
```

Expected result:

```text
[result] vulnerable_revives_terminal_failure=True fixed_blocks_revival=True
```
