//! QA15 (`kcs ledger reconcile`'s orphan/unknown job-attribution walk,
//! 10-operations.md §7.5.2, step4b-contract-tests-p3a.md L323-338): a
//! provider-side Batch job/upload inventory seam.
//!
//! §O future work: no real Adapter "Batch client" trait (upload/job-create/
//! list-jobs/list-uploads) exists in this codebase yet — confirmed by grep,
//! same fact `kcs_pipeline::ledger::ops`'s own module doc records. Both
//! built-in Adapters are single-shot SYNCHRONOUS integrations
//! (`request_kind = 'sync'` batch_requests rows only): Mistral OCR inlines
//! the document bytes as a `data:` URI in one request/response round trip
//! (nothing is retained provider-side afterward), and the Gemini embedding
//! client is a plain `ureq` POST. Neither implements the Batch protocol's
//! async upload -> job-create -> poll -> collect lifecycle
//! (04-pipeline.md §5.8), so there is nothing provider-side to enumerate in
//! production today — see [`configured_inventories`]'s own doc comment for
//! why an empty `Vec` is the correct production answer, not a placeholder.

use serde::Deserialize;

use crate::Result;

/// 10 §7.5.2's job "帰属" (attribution) key: the same 4-tuple task identity
/// `kcs_pipeline::ledger::TaskKey`/`batch_requests`'s PRIMARY KEY uses.
/// Duplicated here (not imported) rather than depended on, because the crate
/// dependency runs the other way (`kcs-pipeline` depends on `kcs-adapter`,
/// not vice versa) — see `kcs_pipeline::ledger::ops::resolve_billing_from_reported_usage`'s
/// doc comment for the same one-directional-dependency note on the adapter
/// side of this boundary.
#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
pub struct ProviderTaskKey {
    pub scope_id: String,
    pub adapter_kind: String,
    pub input_hash: String,
    pub tool_profile_hash: String,
}

/// One provider-side Batch job. `intent_token`/`task_key` mirror whatever
/// job metadata (custom_id, labels, ...) a real Batch client would have
/// attached at submission time — 10 §7.5.2: "job の帰属は token 形式ではなく
/// job metadata の task key 4 組が担う...UUIDv7 token 単独では帰属できない".
/// `intent_token` is kept anyway (not just `task_key`) because §5.8's
/// `recovery_candidates` walk (QA15 step c, the OTHER direction of this
/// matching — "does the provider have MY row's job") still matches
/// found/confirmed-absent primarily by `intent_token`, exactly as
/// `04-pipeline.md §5.8`'s "found (job 取得/一覧で intent_token 一致)" rule
/// states; `task_key` alone would not answer that direction.
#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
pub struct ProviderJobRecord {
    pub job_id: String,
    #[serde(default)]
    pub intent_token: Option<String>,
    #[serde(default)]
    pub task_key: Option<ProviderTaskKey>,
}

/// One provider-side upload. `filename_token` is the `intent_token` a real
/// upload's filename would embed (10 §7.5.2 / 04 §5.8: "intent_token 埋込
/// filename が upload 残骸の唯一の発見キー") — the ONLY attribution an upload
/// carries; unlike a job, an upload has no separate structured metadata to
/// fall back on, so a missing/unmatched `filename_token` is unconditionally
/// `unknown` (10 §7.5.2: "filename の token しか持たない upload は帰属不能
/// (unknown) として報告のみ").
#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
pub struct ProviderUploadRecord {
    pub upload_id: String,
    #[serde(default)]
    pub filename_token: Option<String>,
}

/// One configured Batch client's full job/upload listing — 10 §7.5.2's scan
/// set is built from `provider_scope_id` values (the "記録済み provider
/// scope と現在構成の各 Batch client の provider_scope_id を合わせた集合").
#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
pub struct ProviderInventory {
    pub provider_scope_id: String,
    #[serde(default)]
    pub jobs: Vec<ProviderJobRecord>,
    #[serde(default)]
    pub uploads: Vec<ProviderUploadRecord>,
}

/// Env var naming a JSON fixture file (`Vec<ProviderInventory>`, serde) that
/// stands in for [`configured_inventories`]'s real provider calls in tests —
/// see that function's doc comment.
pub const TEST_BATCH_INVENTORY_ENV: &str = "KCS_TEST_BATCH_INVENTORY";

/// `kcs ledger reconcile`'s (QA15) provider-side job/upload listing for
/// every currently-configured Batch-capable Adapter client.
///
/// **Production always returns an empty `Vec` — this is a correct answer,
/// not a stub.** Walking zero providers is exactly right when zero Batch
/// clients are configured (see this module's doc comment: neither built-in
/// Adapter is Batch-capable). A real Batch-capable Adapter's client (§O
/// future work) would populate this from its own list-jobs/list-uploads
/// calls, scoped per that client's own `provider_scope_id`.
///
/// Honors `KCS_TEST_BATCH_INVENTORY` (a path to a JSON fixture file
/// containing `[{provider_scope_id, jobs: [...], uploads: [...]}, ...]`) so
/// `kcs ledger reconcile`'s orphan/unknown-attribution walk can be exercised
/// deterministically without a real Batch-capable provider — the same
/// "env var names a fixture path" convention `catalog.rs`'s own
/// `TEST_STANDARD_ONLINE_MARKDOWNIZE_ENV`/`TEST_ADOPTED_EMBEDDING_ENV` seams
/// use elsewhere in this crate (those two pass the fixture inline as
/// `"mock"`/JSON text; this one is a path — a full multi-provider inventory
/// fixture is not a one-liner a test would want to inline into an `env()`
/// call).
pub fn configured_inventories() -> Result<Vec<ProviderInventory>> {
    let Ok(fixture_path) = std::env::var(TEST_BATCH_INVENTORY_ENV) else {
        return Ok(Vec::new());
    };
    let text = std::fs::read_to_string(&fixture_path).map_err(|err| crate::AdapterError::Io {
        path: fixture_path.clone(),
        message: err.to_string(),
    })?;
    serde_json::from_str(&text)
        .map_err(|err| crate::AdapterError::ConfigSchema(format!("{fixture_path}: {err}")))
}

#[cfg(test)]
mod tests {
    use std::sync::{Mutex, OnceLock};

    use super::*;

    /// `std::env::set_var`/`remove_var` are process-global, and `cargo test`
    /// runs a crate's `#[test]` functions on multiple threads by default —
    /// without serializing this module's 4 tests (all of which read/write
    /// `TEST_BATCH_INVENTORY_ENV`), one test's `remove_var` can race another's
    /// `set_var`, non-deterministically failing either. Held for each test's
    /// full body (not just the var mutation) so the env state one test
    /// observes cannot change out from under it mid-test.
    fn env_lock() -> &'static Mutex<()> {
        static LOCK: OnceLock<Mutex<()>> = OnceLock::new();
        LOCK.get_or_init(|| Mutex::new(()))
    }

    /// Production default (no env var set): empty inventory, not an error.
    #[test]
    fn production_default_is_empty_not_an_error() {
        let _guard = env_lock().lock().unwrap_or_else(|err| err.into_inner());
        std::env::remove_var(TEST_BATCH_INVENTORY_ENV);
        let inventories = configured_inventories().unwrap();
        assert!(inventories.is_empty());
    }

    /// The test seam parses a well-formed fixture, including the `Option`
    /// fields' `#[serde(default)]` (absent `intent_token`/`task_key`/
    /// `filename_token` deserialize to `None`, not a schema error).
    #[test]
    fn test_seam_parses_a_well_formed_fixture() {
        let _guard = env_lock().lock().unwrap_or_else(|err| err.into_inner());
        let dir = tempfile::tempdir().unwrap();
        let fixture_path = dir.path().join("inventory.json");
        std::fs::write(
            &fixture_path,
            r#"[
                {
                    "provider_scope_id": "scope-a",
                    "jobs": [
                        {
                            "job_id": "job-1",
                            "intent_token": "01HZZZ",
                            "task_key": {
                                "scope_id": "local-scope",
                                "adapter_kind": "markdownize",
                                "input_hash": "sha256:abc",
                                "tool_profile_hash": "sha256:def"
                            }
                        },
                        { "job_id": "job-2" }
                    ],
                    "uploads": [
                        { "upload_id": "upload-1", "filename_token": "01HZZZ" },
                        { "upload_id": "upload-2" }
                    ]
                }
            ]"#,
        )
        .unwrap();
        std::env::set_var(TEST_BATCH_INVENTORY_ENV, &fixture_path);
        let inventories = configured_inventories().unwrap();
        std::env::remove_var(TEST_BATCH_INVENTORY_ENV);

        assert_eq!(inventories.len(), 1);
        let inventory = &inventories[0];
        assert_eq!(inventory.provider_scope_id, "scope-a");
        assert_eq!(inventory.jobs.len(), 2);
        assert_eq!(inventory.jobs[0].job_id, "job-1");
        assert_eq!(inventory.jobs[0].intent_token.as_deref(), Some("01HZZZ"));
        assert_eq!(
            inventory.jobs[0].task_key,
            Some(ProviderTaskKey {
                scope_id: "local-scope".to_owned(),
                adapter_kind: "markdownize".to_owned(),
                input_hash: "sha256:abc".to_owned(),
                tool_profile_hash: "sha256:def".to_owned(),
            })
        );
        assert_eq!(inventory.jobs[1].job_id, "job-2");
        assert_eq!(inventory.jobs[1].intent_token, None);
        assert_eq!(inventory.jobs[1].task_key, None);
        assert_eq!(inventory.uploads.len(), 2);
        assert_eq!(
            inventory.uploads[0].filename_token.as_deref(),
            Some("01HZZZ")
        );
        assert_eq!(inventory.uploads[1].filename_token, None);
    }

    /// A missing fixture path (env var set but the file does not exist) is a
    /// loud error, never silently treated as "empty" — an operator who set
    /// the env var expected fixture content to be honored.
    #[test]
    fn missing_fixture_file_is_a_loud_error() {
        let _guard = env_lock().lock().unwrap_or_else(|err| err.into_inner());
        std::env::set_var(TEST_BATCH_INVENTORY_ENV, "/nonexistent/path/inventory.json");
        let result = configured_inventories();
        std::env::remove_var(TEST_BATCH_INVENTORY_ENV);
        assert!(result.is_err());
    }

    /// Malformed JSON is a loud `ConfigSchema` error, not a panic or a
    /// silent empty inventory.
    #[test]
    fn malformed_fixture_json_is_a_config_schema_error() {
        let _guard = env_lock().lock().unwrap_or_else(|err| err.into_inner());
        let dir = tempfile::tempdir().unwrap();
        let fixture_path = dir.path().join("bad.json");
        std::fs::write(&fixture_path, "{ not valid json").unwrap();
        std::env::set_var(TEST_BATCH_INVENTORY_ENV, &fixture_path);
        let result = configured_inventories();
        std::env::remove_var(TEST_BATCH_INVENTORY_ENV);
        match result {
            Err(crate::AdapterError::ConfigSchema(_)) => {}
            other => panic!("expected ConfigSchema error, got {other:?}"),
        }
    }
}
