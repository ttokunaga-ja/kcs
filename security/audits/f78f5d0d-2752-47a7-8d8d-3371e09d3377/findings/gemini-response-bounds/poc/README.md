# Gemini response-bound regression harness

This offline harness models the ordering required of a repaired Gemini
embedding response path:

1. finish the response read within an overall deadline;
2. reject decoded bodies larger than the byte budget;
3. decode JSON only after those transport/resource checks; and
4. retain count, type, and dimension checks afterward.

It uses only Python's standard library, in-memory byte streams, a 160-byte
body ceiling, and one 100 ms synthetic delay. It does not open a socket, read
KCS state, use an API credential, or invoke the live adapter. It is a
regression model for the proposed control ordering, not a production timeout
implementation.

## Run

From this `poc` directory:

```sh
make test
```

or:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 run.py
```

Expected output:

```text
[PASS] exact-limit response accepted, then passed semantic validation
[PASS] oversized response rejected before semantic validation
[PASS] delayed response rejected by 20 ms deadline before semantic validation
[PASS] wrong-width vector rejected after transport bounds
[PASS] 4 bounded in-memory regressions; no network or credentials used
```

No cleanup is required.
