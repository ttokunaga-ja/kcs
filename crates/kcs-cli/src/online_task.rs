//! Typed ownership checks for standard online markdownize task lifecycles.

use std::path::Path;

use kcs_pipeline::task::{validate_task_output_ref, TaskDescriptor, TaskOutputRef};

/// Identify a markdownize task that the standard online executor owns across both
/// output-ref phases. Fresh tasks carry the online placeholder; a Partial task requeued
/// for a unit-scoped retry must retain its normalized-instance reference so the complete
/// prepared-unit manifest remains loadable. `bbox_annotation_enabled` is stamped only on
/// online markdownize tasks, and `unit_keys` is stamped when such a normalized task is
/// made retryable.
pub(crate) fn targets_standard_online_markdownize(
    kcs_dir: &Path,
    task: &TaskDescriptor,
    placeholder: &str,
) -> bool {
    match validate_task_output_ref(kcs_dir, task) {
        Ok(TaskOutputRef::Online { .. }) => task.output_ref == placeholder,
        Ok(TaskOutputRef::NormalizedInstance { .. }) => {
            task.bbox_annotation_enabled.is_some()
                && (task.unit_keys.is_some()
                    || task.fallback_reason.as_deref() == Some("online_adapter_done"))
        }
        Ok(TaskOutputRef::Embedding { .. }) | Err(_) => false,
    }
}
