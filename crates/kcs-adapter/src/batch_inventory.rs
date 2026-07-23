//! QA15 (`kcs ledger reconcile`'s orphan/unknown job-attribution walk,
//! 10-operations.md §7.5.2, step4b-contract-tests-p3a.md L323-338): a
//! provider-side Batch job/upload inventory seam.
//!
//! Historical note (§O): until the Batch send lane landed, no real Adapter
//! "Batch client" existed — both built-in Adapters were single-shot
//! synchronous integrations, so production correctly enumerated zero
//! providers. Since `batch_client::EnvMistralBatchClient` (07 §5.7, the
//! 2026-07-23 Batch-lane ruling), production enumerates the configured
//! Mistral Batch client's own list-jobs / list-uploads calls — one
//! [`ProviderInventory`] per configured client (currently 0 or 1: the
//! built-in Mistral lane), scoped by that client's `provider_scope_id`. The
//! `KCS_TEST_BATCH_INVENTORY` fixture seam takes precedence when set so the
//! walk stays deterministic in tests.

use serde::Deserialize;

use crate::batch_client::{BatchJobRecord, MistralBatchClient};
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

/// One provider-side Batch job. `intent_token`/`task_key` come from the job
/// metadata the submit lane attaches at job-create time — the fixed 5-key
/// flat schema `{"intent_token", "scope_id", "adapter_kind", "input_hash",
/// "tool_profile_hash"}` (the CLI sends exactly this schema; see
/// [`provider_job_record`]) — 10 §7.5.2: "job の帰属は token 形式ではなく
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
/// The `KCS_TEST_BATCH_INVENTORY` fixture seam wins when set (a path to a
/// JSON fixture file containing `[{provider_scope_id, jobs: [...],
/// uploads: [...]}, ...]`) so `kcs ledger reconcile`'s orphan/unknown-
/// attribution walk can be exercised deterministically without a real
/// provider — the same "env var carries the fixture" convention as
/// `catalog.rs`'s `TEST_STANDARD_ONLINE_MARKDOWNIZE_ENV`/
/// `TEST_ADOPTED_EMBEDDING_ENV` seams (those two pass inline text; this one
/// is a path — a full multi-provider inventory fixture is not a one-liner a
/// test would want to inline into an `env()` call).
///
/// Without the seam, this walks [`crate::batch_client::configured_mistral_batch_client`]:
/// `None` (the Mistral adapter is unconfigured) is an empty `Vec` — walking
/// zero providers is a correct answer, not a stub — and `Some` yields
/// exactly one [`ProviderInventory`] built from that client's own
/// `provider_scope_id` + `list_jobs` + `list_uploads` calls. Note the
/// `KCS_TEST_MISTRAL_BATCH` mock script therefore also reaches here (it IS
/// the configured client when set), which is how the metadata→attribution
/// mapping is tested hermetically.
pub fn configured_inventories() -> Result<Vec<ProviderInventory>> {
    if let Ok(fixture_path) = std::env::var(TEST_BATCH_INVENTORY_ENV) {
        let text =
            std::fs::read_to_string(&fixture_path).map_err(|err| crate::AdapterError::Io {
                path: fixture_path.clone(),
                message: err.to_string(),
            })?;
        return serde_json::from_str(&text)
            .map_err(|err| crate::AdapterError::ConfigSchema(format!("{fixture_path}: {err}")));
    }
    let Some(client) = crate::batch_client::configured_mistral_batch_client()? else {
        return Ok(Vec::new());
    };
    Ok(vec![inventory_from_client(client.as_ref())?])
}

/// One configured client's full listing, mapped to the reconcile walk's
/// records.
fn inventory_from_client(client: &dyn MistralBatchClient) -> Result<ProviderInventory> {
    let provider_scope_id = client.provider_scope_id()?;
    let jobs = client
        .list_jobs()?
        .into_iter()
        .map(provider_job_record)
        .collect();
    let uploads = client
        .list_uploads()?
        .into_iter()
        .map(|upload| ProviderUploadRecord {
            // 04 §5.8 / 10 §7.5.2: the filename-embedded intent token is the
            // ONLY attribution an upload carries; a foreign filename maps to
            // `None` = unknown, report-only.
            filename_token: crate::batch_client::filename_intent_token(&upload.filename)
                .map(str::to_owned),
            upload_id: upload.upload_id,
        })
        .collect();
    Ok(ProviderInventory {
        provider_scope_id,
        jobs,
        uploads,
    })
}

/// Job attribution reads the fixed 5-key flat metadata schema the submit
/// lane attaches at job-create (`intent_token` + the task key 4 組
/// `{"scope_id", "adapter_kind", "input_hash", "tool_profile_hash"}` — the
/// CLI sends this same schema; it is the contract between the two sides).
/// Any key that cannot be read as a string stays `None`: a partial 4 組 is
/// no `task_key` at all (unknown attribution, report-only — 10 §7.5.2),
/// never a guessed one.
fn provider_job_record(job: BatchJobRecord) -> ProviderJobRecord {
    let field = |key: &str| Some(job.metadata.get(key)?.as_str()?.to_owned());
    let intent_token = field("intent_token");
    let task_key = (|| {
        Some(ProviderTaskKey {
            scope_id: field("scope_id")?,
            adapter_kind: field("adapter_kind")?,
            input_hash: field("input_hash")?,
            tool_profile_hash: field("tool_profile_hash")?,
        })
    })();
    ProviderJobRecord {
        job_id: job.job_id,
        intent_token,
        task_key,
    }
}

#[cfg(test)]
mod tests {
    use std::sync::Mutex;

    use super::*;

    /// `std::env::set_var`/`remove_var` are process-global, and `cargo test`
    /// runs a crate's `#[test]` functions on multiple threads by default.
    /// This module's tests share `TEST_BATCH_INVENTORY_ENV` with each other
    /// AND (since the production wiring) `KCS_TEST_MISTRAL_BATCH` /
    /// `MISTRAL_API_KEY` with `batch_client`'s own tests — so the lock must
    /// be the CRATE-wide one (`batch_client::test_env_lock`), not a
    /// module-local mutex a sibling module's tests would never contend on.
    /// Held for each test's full body so the env state one test observes
    /// cannot change out from under it mid-test.
    fn env_lock() -> &'static Mutex<()> {
        crate::batch_client::test_env_lock()
    }

    /// Production default (no seam, no Mistral credential): empty inventory,
    /// not an error. Clears every activation path this walk consults —
    /// the fixture seam, the inline batch mock, and the sync-path credential
    /// condition (`MISTRAL_API_KEY`; no `tools.toml` adapter is registered in
    /// this test binary) — so the assertion holds on machines with ambient
    /// developer env too.
    #[test]
    fn production_default_is_empty_not_an_error() {
        let _guard = env_lock().lock().unwrap_or_else(|err| err.into_inner());
        std::env::remove_var(TEST_BATCH_INVENTORY_ENV);
        std::env::remove_var(crate::batch_client::TEST_MISTRAL_BATCH_ENV);
        std::env::remove_var("MISTRAL_API_KEY");
        let inventories = configured_inventories().unwrap();
        assert!(inventories.is_empty());
    }

    /// Production wiring (no fixture seam): one inventory per configured
    /// Batch client, jobs attributed through the 5-key metadata schema and
    /// uploads through the filename-embedded intent token. The configured
    /// client here is the hermetic `KCS_TEST_MISTRAL_BATCH` mock listing.
    #[test]
    fn configured_client_listing_maps_metadata_and_filename_attribution() {
        let _guard = env_lock().lock().unwrap_or_else(|err| err.into_inner());
        std::env::remove_var(TEST_BATCH_INVENTORY_ENV);
        let script = serde_json::json!({
            "provider_scope_id": "ws-live",
            "jobs_listing": [
                {
                    "job_id": "batch-attributed",
                    "status": "SUCCESS",
                    "output_file_id": "file-out-1",
                    "metadata": {
                        "intent_token": "01HTOKEN",
                        "scope_id": "01HSCOPE",
                        "adapter_kind": "markdownize",
                        "input_hash": "sha256:abc",
                        "tool_profile_hash": "sha256:def"
                    }
                },
                { "job_id": "batch-foreign", "status": "QUEUED" },
                {
                    "job_id": "batch-partial",
                    "status": "RUNNING",
                    "metadata": { "intent_token": "01HONLY", "scope_id": "01HSCOPE" }
                }
            ],
            "uploads_listing": [
                { "upload_id": "file-kcs", "filename": "kcs-01HTOKEN.jsonl" },
                { "upload_id": "file-stray", "filename": "notes.bin" }
            ]
        });
        std::env::set_var(
            crate::batch_client::TEST_MISTRAL_BATCH_ENV,
            script.to_string(),
        );
        let inventories = configured_inventories().unwrap();
        std::env::remove_var(crate::batch_client::TEST_MISTRAL_BATCH_ENV);

        assert_eq!(inventories.len(), 1);
        let inventory = &inventories[0];
        assert_eq!(inventory.provider_scope_id, "ws-live");
        assert_eq!(inventory.jobs.len(), 3);
        assert_eq!(inventory.jobs[0].job_id, "batch-attributed");
        assert_eq!(inventory.jobs[0].intent_token.as_deref(), Some("01HTOKEN"));
        assert_eq!(
            inventory.jobs[0].task_key,
            Some(ProviderTaskKey {
                scope_id: "01HSCOPE".to_owned(),
                adapter_kind: "markdownize".to_owned(),
                input_hash: "sha256:abc".to_owned(),
                tool_profile_hash: "sha256:def".to_owned(),
            })
        );
        // No metadata at all → fully unknown attribution.
        assert_eq!(inventory.jobs[1].intent_token, None);
        assert_eq!(inventory.jobs[1].task_key, None);
        // A partial 4 組 yields NO task_key (never a guessed one); the
        // intent_token still matches §5.8's recovery_candidates direction.
        assert_eq!(inventory.jobs[2].intent_token.as_deref(), Some("01HONLY"));
        assert_eq!(inventory.jobs[2].task_key, None);
        assert_eq!(inventory.uploads.len(), 2);
        assert_eq!(
            inventory.uploads[0].filename_token.as_deref(),
            Some("01HTOKEN")
        );
        assert_eq!(inventory.uploads[1].filename_token, None);
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
