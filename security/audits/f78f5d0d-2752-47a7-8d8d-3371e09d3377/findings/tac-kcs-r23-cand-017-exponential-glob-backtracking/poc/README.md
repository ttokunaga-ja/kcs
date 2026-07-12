# Bounded recursive glob backtracking probe

This is a local, offline reproduction of the vulnerable `wildcard_match_bytes`
shape used by KCS ignore matching. It does not read a real scope and does not
call any service. The default run is intentionally bounded at `n=18`.

```sh
make
./kcs-glob-backtracking-probe
```

The probe constructs failing cases of the form `(*a)^n b` against `a^n`,
counts recursive calls, and checks the validated recurrence
`C(n)=2^(n+2)-3`.

The measurements are diagnostic only. Do not raise the bound on a shared
machine: larger values grow exponentially and can consume substantial CPU.
