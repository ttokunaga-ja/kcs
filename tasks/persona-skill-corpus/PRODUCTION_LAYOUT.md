# Rust workspace layout

`kio-eval persona scaffold --plan <absolute-plan> --root <absolute-root>` is
the only producer of this workspace. It accepts an absolute, new root and
publishes an exact create-only tree. Runbooks and Python do not create,
complete, or reinterpret it.

```text
<workspace-root>/
  persona-plan.json
  persona-workspace-owner.json
  _control/
    personas/
      <persona-id>/
    scopes/
      <persona-id>/
        <rust-scope-id>/
  people/
    <persona-id>-<role>/
      home/
        <scope-path>/
```

The exact persona IDs, role slugs, Rust scope IDs, and `scope-path` values are
read from the accepted plan; the illustrative names above are not a second
schema. `persona-plan.json` and `persona-workspace-owner.json` are Rust-owned
records and must not be edited.

`_control/`, `_control/personas/`, `_control/scopes/`, and each
`_control/scopes/<persona-id>/` are sealed routing directories. The direct
persona and scope leaf directories beneath them are mutable only for the
opaque lease implementation. No additional operator-managed record hierarchy
is created by the scaffold or required for production.

For a plan row, final content belongs only in the corresponding
`people/<persona-id>-<role>/home/<scope-path>/`. The scope's control directory
is selected by its separate Rust scope ID:

```bash
python3 -m eval.persona_skill_corpus_lease scope-claim \
  --root <workspace-root> --persona <persona-id> \
  --scope-id <rust-scope-id> \
  --owner-digest sha256:<lowercase-hash-of-owner-bytes> \
  --parent-session <parent-session> --worker-session <worker-session>
```

The lease is duplicate-writer coordination, not a semantic plan parser or
authorization for Kio replay. Filesystem attestation is separately bound to
the exact `persona-materialization.json` digest and makes no Kio/history claim.
