# Synthetic persisted OCR ignore-bypass probe

This probe is a local regression model for the stale authorization bug. It does
not run KCS, contact an OCR provider, or require credentials.

Run it from this directory:

```sh
make
```

Expected result:

```text
[+] created synthetic OCR-eligible task for private-plan.pdf
[+] current ignore policy excludes private-plan.pdf
[+] vulnerable gate decision: Send
[+] fixed gate decision: Retire
[+] regression expectation satisfied without network or credentials
```
