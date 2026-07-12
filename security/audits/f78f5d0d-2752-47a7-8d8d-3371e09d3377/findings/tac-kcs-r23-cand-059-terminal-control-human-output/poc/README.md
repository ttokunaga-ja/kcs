# Safe Terminal-Control Encoding Probe

This probe models the KCS branch difference without printing any live terminal
control sequence. It keeps the synthetic payload as bytes, prints only a hex
view of those bytes, and compares that with JSON escaped output.

Run:

```sh
make run
```

Expected result: the raw branch contains ESC and BEL bytes, while the JSON
branch contains no raw ESC byte.
