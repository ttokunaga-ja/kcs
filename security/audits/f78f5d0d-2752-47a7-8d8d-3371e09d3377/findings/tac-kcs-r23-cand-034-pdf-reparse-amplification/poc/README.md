# PDF page marker amplification probe

This is a bounded local regression probe for KCS-R23-CAND-034. It creates
synthetic PDF-like bytes in memory, counts lexical `/Page` markers with the
same relevant prefix behavior, and reports the derived unit and extraction
relationship. It does not run KCS, read a repository store, use credentials, or
contact a network.

Run:

```sh
make
make run
```

The default run uses 63 false markers, matching the bounded validation
relationship. The script refuses very large marker counts so it remains safe as
a review artifact.

