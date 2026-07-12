# Bounded status/snapshot whole-file-read probe

This local regression sample creates one disposable 262,144-byte regular file,
runs `kcs status`, and then runs `kcs snapshot`. The size is a fixed constant in
`run.sh`; the script accepts no size override. It does not create a sparse file,
measure a failure threshold, or attempt resource exhaustion.

The sample records two safe reachability signals:

- whether status returns the SHA-256 hash of the complete fixture; and
- whether snapshot creates a raw object whose size equals the complete fixture.

Those observations show that both command paths process the entire direct-child
file. They do not, by themselves, distinguish `fs::read` from a safe streaming
implementation. Review or unit-test the implementation's allocation bound when
validating a streaming-only fix.

## Run

Build KCS from the revision under test, put the resulting `kcs` command on
`PATH`, and run:

```sh
cd poc
make run
```

Alternatively, name the command explicitly:

```sh
cd poc
make run KCS_BIN=relative/path/to/kcs
```

All KCS state is redirected into a temporary directory and removed on exit.
The commands are offline core operations and the sample uses only synthetic
bytes.

## Interpret the result

The confirmed vulnerable revision produces the values in
`representative-output.txt`. `WHOLE_FILE_STATUS_AND_SNAPSHOT_PATH_REACHED`
means the complete bounded file reached both paths. If a cap-based fix rejects
the file before hashing or archive storage, the script instead reports
`OVERSIZE_REJECTED_BY_BOTH_COMMANDS`.

A streaming fix may intentionally preserve the first result while still
removing the memory-allocation defect. In that design, pair this sample with a
unit test that injects a counting reader and asserts a fixed buffer ceiling and
an aggregate byte budget.
