# Offline model-catalog bounds probe

This directory contains a harmless, deterministic regression oracle for the
model-resolution response invariants. It does **not** contact Mistral or any
other endpoint, read environment variables, use credentials, import KCS, or
sleep. The largest generated response body is fixed at 128 KiB, so the parser
demonstration and its overhead remain small and bounded.

Run it from the report directory:

```sh
cd poc
python3 bounded_model_catalog_probe.py
```

Expected output:

```text
[+] vulnerable ordering: materialized 131072 bytes before selecting mistral-ocr-2505 (demo hard-capped)
[+] decoded-byte regression: rejected: decoded body exceeds 4096 bytes
[+] gzip-expansion regression: rejected: decoded body exceeds 4096 bytes
[+] deadline regression: rejected: chunk arrived at 1001 ms; deadline is 1000 ms
[+] valid-catalog regression: selected mistral-ocr-2505
[+] PASS: offline byte, decompression, and deadline invariants hold
```

The first line models the current ordering at a deliberately small ceiling:
the complete JSON value exists before model-family filtering begins. The next
three checks are regression oracles for a repaired implementation: reject a
decoded body over its limit, reject compressed expansion over that same limit,
and stop when a response crosses a deadline. The clock is data carried by the
test, so the deadline check completes immediately.

This is not a live exploit and does not claim to measure KCS memory use or
network timing. A KCS unit test can reuse the same cases after response reading
is extracted behind a `Read`-based bounded helper. The transport test should
inject a reader that returns `io::ErrorKind::TimedOut`; no socket is needed.
Tests should cover an exact-limit response, a limit-plus-one response, a small
gzip stream that expands beyond the decoded limit, a timeout before complete
JSON, a valid small catalog, and a fixed model pin that performs no catalog
read. There is no cleanup step.
