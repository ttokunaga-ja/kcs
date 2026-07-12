# Offline consent-state regression

This regression models the two exact store-local acceptance predicates in the
confirmed source revision:

- `approval_row_present_in_kcs_dir` for persistent network consent; and
- `secrets_send_approved` for secret-release consent.

It compares three synthetic cases: a foreign row copied into a different
scope, a whole `.kcs` copied to another root, and a fully preseeded store whose
identity and rows were chosen together. It also evaluates a fixed-state oracle
where authority lives in protected device-local state bound to the canonical
root and scope identity.

The script is deliberately harmless. It uses only the Python standard library,
creates state below an automatically cleaned temporary directory, does not run
the KCS binary, and has no adapter, socket, service, or credential path.

Run it from the report directory:

```sh
cd poc
python3 consent_state_regression.py
```

Python 3.9 or newer is sufficient. A successful run exits zero after showing
that the current predicates reject the row-only negative control but accept
both same-store replay and forgery. See `representative-output.txt` for the
expected output.

This is a source-faithful state regression, not an end-to-end outbound-send
test. It intentionally does not model repository schema completeness, adapter
configuration, credential attachment, revocation, or the later network call.
