# Gemini Vector Domain Probe

This PoC is local and offline. It does not contact Gemini, require credentials,
load sqlite-vec, or modify a KCS repository. It models the vulnerable KCS
invariant with a four-dimensional synthetic vector:

- accept JSON numeric values;
- narrow each value from f64 to f32;
- check only vector width;
- show why non-finite or zero-norm vectors should be rejected before cosine
  search or persistence.

Run it from this directory:

```sh
make
```

Expected output includes the vulnerable parser accepting an over-range finite
JSON number that becomes `inf`, an exact-width zero vector, and a finite basis
control. The hardened validator rejects the two malformed vectors and accepts
the control vector.
