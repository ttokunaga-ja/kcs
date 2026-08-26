//! Compile-time release-candidate binding retained for the external verifier.

include!(concat!(env!("OUT_DIR"), "/release_binding_generated.rs"));

/// Keep the release binding in the executable without exposing a user-facing API.
pub(crate) fn retain() {
    std::hint::black_box(RELEASE_BINDING.as_bytes());
}
