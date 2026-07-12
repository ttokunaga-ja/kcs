# Snapshot symlink-race PoC

This is a local/offline deterministic model of the KCS snapshot check/use
interleaving. It does not run the KCS CLI, touch repository state, use
credentials, or access a network service.

Run:

```sh
make run
```

The script creates a temporary synthetic scope, observes `report.txt` as a
regular direct child, replaces that name with a symlink to `../outside-victim.txt`,
and then performs a pathname read that follows the replacement. A vulnerable
snapshot implementation that separates the regular-file check from the later
pathname read can archive those outside bytes under the benign `report.txt`
tree name.
