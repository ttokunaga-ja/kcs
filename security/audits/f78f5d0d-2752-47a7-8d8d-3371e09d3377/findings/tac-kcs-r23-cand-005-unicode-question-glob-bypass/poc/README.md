# Unicode `?` Glob Bypass PoC

This PoC is local and offline. It mirrors the vulnerable KCS byte-oriented
matcher for `?` and compares it with a Unicode-scalar matcher using synthetic
filenames only.

Run:

```sh
make test
```

Expected result: `a.txt` is ignored by both matchers, while `é.txt`,
decomposed `é.txt`, and `😀.txt` are not ignored by the vulnerable matcher but
are ignored by the scalar-aware matcher.
