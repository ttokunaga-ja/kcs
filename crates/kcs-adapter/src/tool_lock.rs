//! `tool-lock.json` identity and validation contracts.

use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};

use crate::identity::jcs_hash;
use crate::types::ExecutionMode;
use crate::{AdapterError, Result};

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ToolLock {
    pub spec_version: u64,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub prepare: Option<PrepareToolLockEntry>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub markdown: Option<MarkdownToolLockEntry>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub embedding: Option<EmbeddingToolLockEntry>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct PrepareToolLockEntry {
    pub tool_id: String,
    pub profile_hash: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub kind: Option<ExecutionMode>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct MarkdownToolLockEntry {
    pub tool_id: String,
    pub profile_hash: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub kind: Option<ExecutionMode>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub capabilities: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct EmbeddingToolLockEntry {
    pub tool_id: String,
    pub dimensions: u32,
    pub distance: String,
    pub modality: String,
    pub profile_hash: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub kind: Option<ExecutionMode>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub mode: Option<String>,
}

pub fn load_tool_lock(bytes: &[u8]) -> Result<ToolLock> {
    let value: Value =
        serde_json::from_slice(bytes).map_err(|err| AdapterError::ConfigSchema(err.to_string()))?;
    validate_tool_lock_value(&value)?;
    serde_json::from_value(value).map_err(|err| AdapterError::ConfigSchema(err.to_string()))
}

pub fn tool_lock_hash_from_bytes(bytes: &[u8]) -> Result<String> {
    let value: Value =
        serde_json::from_slice(bytes).map_err(|err| AdapterError::ConfigSchema(err.to_string()))?;
    tool_lock_hash(&value)
}

pub fn tool_lock_hash(value: &Value) -> Result<String> {
    validate_tool_lock_value(value)?;
    jcs_hash(&canonical_tool_lock_value(value)?)
}

pub fn canonical_tool_lock_value(value: &Value) -> Result<Value> {
    let object = value
        .as_object()
        .ok_or_else(|| AdapterError::ConfigSchema("tool-lock.json must be an object".to_owned()))?;
    let mut canonical = Map::new();
    let spec_version = object
        .get("spec_version")
        .and_then(Value::as_u64)
        .ok_or_else(|| {
            AdapterError::ConfigSchema("tool-lock.json missing spec_version".to_owned())
        })?;
    if spec_version != 1 {
        return Err(AdapterError::ConfigSchema(format!(
            "unsupported tool-lock spec_version: {spec_version}"
        )));
    }
    canonical.insert("spec_version".to_owned(), Value::from(spec_version));
    for key in ["prepare", "markdown", "summary", "classification", "rerank"] {
        if let Some(entry) = canonical_simple_entry(object, key)? {
            canonical.insert(key.to_owned(), entry);
        }
    }
    if let Some(entry) = canonical_embedding_entry(object)? {
        canonical.insert("embedding".to_owned(), entry);
    }
    Ok(Value::Object(canonical))
}

pub fn validate_tools_toml(bytes: &[u8]) -> Result<()> {
    let text =
        std::str::from_utf8(bytes).map_err(|err| AdapterError::ConfigSchema(err.to_string()))?;
    let value: toml::Value =
        toml::from_str(text).map_err(|err| AdapterError::ConfigSchema(err.to_string()))?;
    validate_tools_toml_value(&value)
}

/// R13-2: the adapter-role sections `tools.toml` may declare (docs/03 §11 +
/// docs/07 §1/§6). Symmetric with `tool-lock.json` and `config.toml`, an unknown
/// top-level section is rejected (exit 2, `KCS-E-CONFIG-SCHEMA-001`).
const TOOLS_ADAPTER_ROLES: &[&str] = &[
    "prepare",
    "markdown",
    "embedding",
    "summary",
    "classification",
    "rerank",
];

/// R13-2: the documented per-adapter fields (docs/03 §11 + docs/07 §1/§6). Any
/// other field in an adapter entry is a typo/unknown key → rejected. `dimensions`
/// / `distance` / `modality` / `mode` are embedding fields (docs/07 §6).
const TOOLS_ENTRY_FIELDS: &[&str] = &[
    "kind",
    "cmd",
    "args",
    "url",
    "model",
    "auth",
    "profile_hash",
    "capabilities",
    "dimensions",
    "distance",
    "modality",
    "mode",
];

/// R13-2: typed validation of `tools.toml`. docs/06 §11 and docs/10 §12.3 promise
/// a schema-driven check that never existed — the previous validator only walked
/// `auth` prefixes. Before this, a `tools.toml` `[markdown] totally_bogus_key="x"`
/// plus `cmd = 12345` (type-mismatched) were accepted at exit 0 while `config.toml`
/// rejected the same shapes at exit 2. Now unknown sections/fields and wrong types
/// are `KCS-E-CONFIG-SCHEMA-001` (exit 2). Fields are type-checked first, then
/// target-rich declarations are rejected when this build has no matching
/// dispatcher. The `auth`-prefix check is applied only to the `auth` field.
pub fn validate_tools_toml_value(value: &toml::Value) -> Result<()> {
    let table = value
        .as_table()
        .ok_or_else(|| AdapterError::ConfigSchema("tools.toml must be a table".to_owned()))?;
    for (role, section) in table {
        if !TOOLS_ADAPTER_ROLES.contains(&role.as_str()) {
            return Err(AdapterError::ConfigSchema(format!(
                "unknown tools.toml section `{role}` (expected one of: {})",
                TOOLS_ADAPTER_ROLES.join(", ")
            )));
        }
        validate_tools_role_section(role, section)?;
    }
    Ok(())
}

fn validate_tools_role_section(role: &str, section: &toml::Value) -> Result<()> {
    let table = section.as_table().ok_or_else(|| {
        AdapterError::ConfigSchema(format!("tools.toml `{role}` must be a table"))
    })?;
    for (key, val) in table {
        if TOOLS_ENTRY_FIELDS.contains(&key.as_str()) {
            // Single-adapter-per-role form: fields directly under `[role]`.
            validate_tools_entry_field(role, key, val)?;
        } else if val.is_table() {
            // `[role.tool_id]` form: the key is a tool_id naming a nested entry.
            validate_tools_adapter_entry(role, key, val)?;
        } else {
            return Err(AdapterError::ConfigSchema(format!(
                "unknown key `{role}.{key}` in tools.toml \
                 (not a known adapter field, and not a `[{role}.<tool_id>]` table)"
            )));
        }
    }
    let has_direct_fields = table
        .keys()
        .any(|key| TOOLS_ENTRY_FIELDS.contains(&key.as_str()));
    if has_direct_fields {
        if table
            .keys()
            .any(|key| !TOOLS_ENTRY_FIELDS.contains(&key.as_str()))
        {
            return Err(AdapterError::ConfigSchema(format!(
                "tools.toml `{role}` cannot mix direct adapter fields with nested adapter entries"
            )));
        }
        validate_supported_runtime_target(role, None, table)?;
    }
    Ok(())
}

fn validate_tools_adapter_entry(role: &str, tool_id: &str, entry: &toml::Value) -> Result<()> {
    let table = entry.as_table().ok_or_else(|| {
        AdapterError::ConfigSchema(format!("tools.toml `{role}.{tool_id}` must be a table"))
    })?;
    let context = format!("{role}.{tool_id}");
    for (key, val) in table {
        if !TOOLS_ENTRY_FIELDS.contains(&key.as_str()) {
            return Err(AdapterError::ConfigSchema(format!(
                "unknown field `{key}` in tools.toml `{context}`"
            )));
        }
        validate_tools_entry_field(&context, key, val)?;
    }
    validate_supported_runtime_target(role, Some(tool_id), table)?;
    Ok(())
}

fn validate_supported_runtime_target(
    role: &str,
    tool_id: Option<&str>,
    table: &toml::value::Table,
) -> Result<()> {
    let unsupported_target =
        table.contains_key("cmd") || table.contains_key("args") || table.contains_key("url");
    match role {
        "markdown" => {
            if tool_id.is_some_and(|id| id != "mistral_ocr_markdownize") {
                return Err(AdapterError::ConfigSchema(format!(
                    "unsupported markdown adapter `{}`; this build executes only `mistral_ocr_markdownize`",
                    tool_id.unwrap_or_default()
                )));
            }
            if unsupported_target {
                return Err(AdapterError::ConfigSchema(
                    "markdown cmd/args/url targets are unsupported by the built-in Mistral runtime"
                        .to_owned(),
                ));
            }
            require_online_kind("markdown", table)?;
            if let Some(model) = table.get("model").and_then(toml::Value::as_str) {
                if !model.starts_with("mistral-ocr-") {
                    return Err(AdapterError::ConfigSchema(format!(
                        "unsupported markdown model `{model}` for the built-in Mistral runtime"
                    )));
                }
            }
        }
        "embedding" => {
            if tool_id.is_some_and(|id| id != "gemini_embedding_2") {
                return Err(AdapterError::ConfigSchema(format!(
                    "unsupported embedding adapter `{}`; this build executes only `gemini_embedding_2`",
                    tool_id.unwrap_or_default()
                )));
            }
            if unsupported_target {
                return Err(AdapterError::ConfigSchema(
                    "embedding cmd/args/url targets are unsupported by the built-in Gemini runtime"
                        .to_owned(),
                ));
            }
            require_online_kind("embedding", table)?;
            if let Some(model) = table.get("model").and_then(toml::Value::as_str) {
                if model != "gemini-embedding-2" {
                    return Err(AdapterError::ConfigSchema(format!(
                        "unsupported embedding model `{model}`; expected `gemini-embedding-2`"
                    )));
                }
            }
            if table
                .get("dimensions")
                .and_then(toml::Value::as_integer)
                .is_some_and(|dimensions| dimensions != 768)
            {
                return Err(AdapterError::ConfigSchema(
                    "embedding dimensions must be 768 for `gemini_embedding_2`".to_owned(),
                ));
            }
            if table
                .get("distance")
                .and_then(toml::Value::as_str)
                .is_some_and(|distance| distance != "cosine")
            {
                return Err(AdapterError::ConfigSchema(
                    "embedding distance must be `cosine` for `gemini_embedding_2`".to_owned(),
                ));
            }
            if table
                .get("modality")
                .and_then(toml::Value::as_str)
                .is_some_and(|modality| modality != "multimodal")
            {
                return Err(AdapterError::ConfigSchema(
                    "embedding modality must be `multimodal` for `gemini_embedding_2`".to_owned(),
                ));
            }
            if table
                .get("mode")
                .and_then(toml::Value::as_str)
                .is_some_and(|mode| mode != "online")
            {
                return Err(AdapterError::ConfigSchema(
                    "embedding mode must be `online` for `gemini_embedding_2`".to_owned(),
                ));
            }
        }
        _ => {}
    }
    Ok(())
}

fn require_online_kind(role: &str, table: &toml::value::Table) -> Result<()> {
    if table
        .get("kind")
        .and_then(toml::Value::as_str)
        .is_some_and(|kind| kind != "online_api")
    {
        return Err(AdapterError::ConfigSchema(format!(
            "tools.toml `{role}.kind` must be `online_api` for the built-in runtime"
        )));
    }
    Ok(())
}

fn validate_tools_entry_field(context: &str, key: &str, val: &toml::Value) -> Result<()> {
    match key {
        "kind" | "cmd" | "url" | "model" | "profile_hash" | "distance" | "modality" | "mode" => {
            if !val.is_str() {
                return Err(field_type_error(context, key, "a string"));
            }
        }
        "auth" => {
            // R13-2(e): the `keychain:`/`env:`/`plain:` prefix check is scoped to the
            // Credential reference prefixes are meaningful only on `auth`.
            let Some(auth) = val.as_str() else {
                return Err(field_type_error(context, key, "a string"));
            };
            if !valid_auth_value(auth) {
                return Err(AdapterError::ConfigSchema(
                    "auth must start with keychain:, env:, or plain:".to_owned(),
                ));
            }
        }
        "args" | "capabilities" => {
            let all_strings = val
                .as_array()
                .is_some_and(|items| items.iter().all(toml::Value::is_str));
            if !all_strings {
                return Err(field_type_error(context, key, "an array of strings"));
            }
        }
        "dimensions" => {
            if !val.is_integer() {
                return Err(field_type_error(context, key, "an integer"));
            }
        }
        _ => unreachable!("caller restricted `key` to TOOLS_ENTRY_FIELDS"),
    }
    Ok(())
}

fn field_type_error(context: &str, key: &str, expected: &str) -> AdapterError {
    AdapterError::ConfigSchema(format!("tools.toml `{context}.{key}` must be {expected}"))
}

fn validate_tool_lock_value(value: &Value) -> Result<()> {
    let object = value
        .as_object()
        .ok_or_else(|| AdapterError::ConfigSchema("tool-lock.json must be an object".to_owned()))?;
    let Some(spec_version) = object.get("spec_version").and_then(Value::as_u64) else {
        return Err(AdapterError::ConfigSchema(
            "tool-lock.json spec_version must be an integer".to_owned(),
        ));
    };
    if spec_version != 1 {
        return Err(AdapterError::ConfigSchema(format!(
            "unsupported tool-lock spec_version: {spec_version}"
        )));
    }
    for key in ["prepare", "markdown", "summary", "classification", "rerank"] {
        if let Some(entry) = object.get(key) {
            validate_simple_entry(key, entry)?;
        }
    }
    if let Some(entry) = object.get("embedding") {
        validate_embedding_entry(entry)?;
    }
    Ok(())
}

fn canonical_simple_entry(object: &Map<String, Value>, key: &str) -> Result<Option<Value>> {
    let Some(entry) = object.get(key) else {
        return Ok(None);
    };
    if entry.is_null() {
        return Ok(None);
    }
    let entry = entry
        .as_object()
        .ok_or_else(|| AdapterError::ConfigSchema(format!("{key} entry must be an object")))?;
    let mut canonical = Map::new();
    canonical.insert(
        "tool_id".to_owned(),
        required_string(entry, key, "tool_id")?,
    );
    canonical.insert(
        "profile_hash".to_owned(),
        required_string(entry, key, "profile_hash")?,
    );
    Ok(Some(Value::Object(canonical)))
}

fn canonical_embedding_entry(object: &Map<String, Value>) -> Result<Option<Value>> {
    let Some(entry) = object.get("embedding") else {
        return Ok(None);
    };
    if entry.is_null() {
        return Ok(None);
    }
    let entry = entry.as_object().ok_or_else(|| {
        AdapterError::ConfigSchema("embedding entry must be an object".to_owned())
    })?;
    let mut canonical = Map::new();
    canonical.insert(
        "dimensions".to_owned(),
        required_u64(entry, "embedding", "dimensions")?,
    );
    canonical.insert(
        "distance".to_owned(),
        required_string(entry, "embedding", "distance")?,
    );
    canonical.insert(
        "modality".to_owned(),
        required_string(entry, "embedding", "modality")?,
    );
    canonical.insert(
        "profile_hash".to_owned(),
        required_string(entry, "embedding", "profile_hash")?,
    );
    canonical.insert(
        "tool_id".to_owned(),
        required_string(entry, "embedding", "tool_id")?,
    );
    Ok(Some(Value::Object(canonical)))
}

fn validate_simple_entry(key: &str, value: &Value) -> Result<()> {
    if value.is_null() {
        return Ok(());
    }
    let object = value
        .as_object()
        .ok_or_else(|| AdapterError::ConfigSchema(format!("{key} entry must be an object")))?;
    required_string(object, key, "tool_id")?;
    required_string(object, key, "profile_hash")?;
    Ok(())
}

fn validate_embedding_entry(value: &Value) -> Result<()> {
    if value.is_null() {
        return Ok(());
    }
    let object = value.as_object().ok_or_else(|| {
        AdapterError::ConfigSchema("embedding entry must be an object".to_owned())
    })?;
    required_string(object, "embedding", "tool_id")?;
    required_string(object, "embedding", "profile_hash")?;
    required_u64(object, "embedding", "dimensions")?;
    required_string(object, "embedding", "distance")?;
    let modality = required_string(object, "embedding", "modality")?;
    // 03 §7: modality は "multimodal" に固定。別ベクトル空間 (text 専用等) の
    // embedding profile は tool-lock materialize の時点で採用拒否する。
    if modality.as_str() != Some("multimodal") {
        return Err(AdapterError::ConfigSchema(format!(
            "KCS-E-EMBED-MODALITY-001: embedding.modality must be \"multimodal\" \
             (got {modality}); non-multimodal embedding profiles are not adoptable"
        )));
    }
    Ok(())
}

fn required_string(object: &Map<String, Value>, entry: &str, field: &str) -> Result<Value> {
    let value = object
        .get(field)
        .and_then(Value::as_str)
        .ok_or_else(|| AdapterError::ConfigSchema(format!("{entry}.{field} must be a string")))?;
    Ok(Value::String(value.to_owned()))
}

fn required_u64(object: &Map<String, Value>, entry: &str, field: &str) -> Result<Value> {
    let value = object
        .get(field)
        .and_then(Value::as_u64)
        .ok_or_else(|| AdapterError::ConfigSchema(format!("{entry}.{field} must be an integer")))?;
    Ok(Value::from(value))
}

fn valid_auth_value(value: &str) -> bool {
    ["keychain:", "env:", "plain:"]
        .iter()
        .any(|prefix| value.starts_with(prefix) && value.len() > prefix.len())
}

/// R13-2: a declared adapter entry from `tools.toml`, resolved for a single
/// adapter role. `tool_id` is the `[role.tool_id]` key (or the role name for the
/// single-adapter form). Execution-target fields are preserved as well as
/// model/auth so the runtime can prove that its effective recipient matches the
/// accepted declaration instead of silently projecting target identity away.
#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct DeclaredAdapter {
    pub tool_id: Option<String>,
    pub kind: Option<String>,
    pub cmd: Option<String>,
    pub args: Vec<String>,
    pub url: Option<String>,
    pub model: Option<String>,
    pub auth: Option<String>,
}

/// R13-2: locate the declared adapter for `role` in an already-parsed `tools.toml`
/// (`markdown` / `embedding` / …). Returns the complete execution identity so
/// the CLI can recheck recipient, credential, and model together. Accepts both documented
/// shapes: fields directly under `[role]` (single adapter) and a single
/// `[role.tool_id]` table. `None` when the role is not declared. Assumes the value
/// already passed [`validate_tools_toml_value`].
#[must_use]
pub fn declared_adapter_for_role(value: &toml::Value, role: &str) -> Option<DeclaredAdapter> {
    let section = value.as_table()?.get(role)?.as_table()?;
    // Single-adapter form: documented fields sit directly under `[role]`.
    let has_direct_fields = section
        .keys()
        .any(|key| TOOLS_ENTRY_FIELDS.contains(&key.as_str()));
    if has_direct_fields {
        return Some(DeclaredAdapter {
            tool_id: None,
            kind: optional_string(section, "kind"),
            cmd: optional_string(section, "cmd"),
            args: optional_string_array(section, "args"),
            url: optional_string(section, "url"),
            model: section
                .get("model")
                .and_then(toml::Value::as_str)
                .map(str::to_owned),
            auth: section
                .get("auth")
                .and_then(toml::Value::as_str)
                .map(str::to_owned),
        });
    }
    // `[role.tool_id]` form: take the first declared tool_id (MVP: one per role).
    let (tool_id, entry) = section.iter().next()?;
    let entry = entry.as_table()?;
    Some(DeclaredAdapter {
        tool_id: Some(tool_id.clone()),
        kind: optional_string(entry, "kind"),
        cmd: optional_string(entry, "cmd"),
        args: optional_string_array(entry, "args"),
        url: optional_string(entry, "url"),
        model: entry
            .get("model")
            .and_then(toml::Value::as_str)
            .map(str::to_owned),
        auth: entry
            .get("auth")
            .and_then(toml::Value::as_str)
            .map(str::to_owned),
    })
}

fn optional_string(table: &toml::value::Table, field: &str) -> Option<String> {
    table
        .get(field)
        .and_then(toml::Value::as_str)
        .map(str::to_owned)
}

fn optional_string_array(table: &toml::value::Table, field: &str) -> Vec<String> {
    table
        .get(field)
        .and_then(toml::Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(toml::Value::as_str)
        .map(str::to_owned)
        .collect()
}

/// R13-2: process-global registry of the declared adapters from the user
/// `tools.toml`, keyed by role. The CLI parses `tools.toml` once at startup and
/// registers it here so the online clients can lazily resolve the declared
/// `auth`/`model` at execution time — rather than the previous hard-coded
/// `MISTRAL_API_KEY`/`GEMINI_API_KEY`/`"…-latest"` — without threading the config
/// path (unknown to this crate) through every call site. Empty by default, so the
/// hermetic unit tests and any un-registered process keep the legacy env-var
/// behavior. Lazy resolution keeps a `keychain:` declaration from erroring
/// commands that never touch the adapter.
static DECLARED_ADAPTERS: std::sync::OnceLock<std::collections::HashMap<String, DeclaredAdapter>> =
    std::sync::OnceLock::new();

/// R13-2: register the declared adapters (role → entry) parsed from `tools.toml`.
/// Idempotent-once: the first registration wins (set at CLI startup). Safe no-op
/// if called again.
pub fn register_declared_adapters(map: std::collections::HashMap<String, DeclaredAdapter>) {
    let _ = DECLARED_ADAPTERS.set(map);
}

/// R13-2: the registered declared adapter for `role`, if any (see
/// [`register_declared_adapters`]).
#[must_use]
pub fn registered_declared_adapter(role: &str) -> Option<DeclaredAdapter> {
    DECLARED_ADAPTERS.get()?.get(role).cloned()
}

/// R13-2: resolve the API key for an online adapter `role` — the declared
/// `tools.toml` `auth` when present (env/plain/keychain via [`resolve_auth`],
/// keychain being a loud error), else the legacy `fallback_env` variable. `None`
/// means no credential is available (adapter inactive). This is the single seam
/// the `Env*` clients call so a declared `auth = "env:MY_KEY"` is honored instead
/// of the previous hard-coded variable.
pub fn resolve_role_api_key(role: &str, fallback_env: &str) -> Result<Option<String>> {
    let declared = registered_declared_adapter(role);
    if let Some(declared) = declared.as_ref() {
        validate_declared_runtime_target(role, declared)?;
    }
    resolve_declared_or_env_api_key(declared.as_ref(), fallback_env)
}

pub fn validate_declared_runtime_target(role: &str, declared: &DeclaredAdapter) -> Result<()> {
    let expected_tool = match role {
        "markdown" => Some("mistral_ocr_markdownize"),
        "embedding" => Some("gemini_embedding_2"),
        _ => None,
    };
    if let (Some(expected), Some(actual)) = (expected_tool, declared.tool_id.as_deref()) {
        if actual != expected {
            return Err(AdapterError::ConfigSchema(format!(
                "declared {role} adapter `{actual}` does not match effective runtime `{expected}`"
            )));
        }
    }
    if matches!(role, "markdown" | "embedding")
        && (declared.cmd.is_some() || declared.url.is_some() || !declared.args.is_empty())
    {
        return Err(AdapterError::ConfigSchema(format!(
            "declared {role} target cannot be executed by the built-in runtime"
        )));
    }
    if matches!(role, "markdown" | "embedding")
        && declared
            .kind
            .as_deref()
            .is_some_and(|kind| kind != "online_api")
    {
        return Err(AdapterError::ConfigSchema(format!(
            "declared {role} kind does not match effective `online_api` runtime"
        )));
    }
    if role == "embedding"
        && declared
            .model
            .as_deref()
            .is_some_and(|model| model != "gemini-embedding-2")
    {
        return Err(AdapterError::ConfigSchema(
            "declared embedding model does not match effective `gemini-embedding-2` runtime"
                .to_owned(),
        ));
    }
    if role == "markdown"
        && declared
            .model
            .as_deref()
            .is_some_and(|model| !model.starts_with("mistral-ocr-"))
    {
        return Err(AdapterError::ConfigSchema(
            "declared markdown model is not supported by the Mistral OCR runtime".to_owned(),
        ));
    }
    Ok(())
}

/// R13-2: pure core of [`resolve_role_api_key`] (unit-testable without the
/// process-global registry). A declared `auth` wins (env/plain/keychain via
/// [`resolve_auth`]); otherwise the legacy `fallback_env` variable is read.
pub fn resolve_declared_or_env_api_key(
    declared: Option<&DeclaredAdapter>,
    fallback_env: &str,
) -> Result<Option<String>> {
    if let Some(auth) = declared.and_then(|declared| declared.auth.as_deref()) {
        return resolve_auth(auth);
    }
    Ok(std::env::var(fallback_env).ok())
}

/// R13-2: resolve a `tools.toml` `auth` reference to a concrete API key
/// (docs/07 §1). `env:<NAME>` reads `$NAME`; `plain:<key>` is the literal key;
/// `keychain:<service>` is a LOUD `KCS-E-NOT-IMPLEMENTED-001` (never a silent
/// noop — the previous code ignored the whole declared surface). Returns `None`
/// only when `env:<NAME>` names an unset variable, so the caller can fall back to
/// its legacy hard-coded env var. Adding a `keyring` dependency is out of scope
/// (deferred to a later ruling); explicit "unimplemented" is the safe MVP.
pub fn resolve_auth(auth: &str) -> Result<Option<String>> {
    if let Some(name) = auth.strip_prefix("env:") {
        return Ok(std::env::var(name).ok());
    }
    if let Some(key) = auth.strip_prefix("plain:") {
        return Ok(Some(key.to_owned()));
    }
    if let Some(service) = auth.strip_prefix("keychain:") {
        return Err(AdapterError::NotImplemented(format!(
            "keychain auth (`keychain:{service}`) is not implemented; \
             use `env:<VAR>` or `plain:<key>` in tools.toml"
        )));
    }
    Err(AdapterError::ConfigSchema(
        "auth must start with keychain:, env:, or plain:".to_owned(),
    ))
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn non_multimodal_embedding_entry_is_rejected() {
        // 03 §7: 別ベクトル空間 (modality != "multimodal") の embedding profile は
        // tool-lock materialize の時点で採用拒否 (KCS-E-EMBED-MODALITY-001)。
        let value = json!({
            "spec_version": 1,
            "embedding": {
                "tool_id": "some_text_embedding",
                "profile_hash": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
                "dimensions": 768,
                "distance": "cosine",
                "modality": "text"
            }
        });
        let err = validate_tool_lock_value(&value).expect_err("text modality must be rejected");
        assert!(err.to_string().contains("KCS-E-EMBED-MODALITY-001"));

        let ok = json!({
            "spec_version": 1,
            "embedding": {
                "tool_id": "gemini_embedding_2",
                "profile_hash": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
                "dimensions": 768,
                "distance": "cosine",
                "modality": "multimodal"
            }
        });
        validate_tool_lock_value(&ok).expect("multimodal modality must be accepted");
    }

    #[test]
    fn placeholder_tool_lock_serializes_spec_version() {
        let lock = ToolLock {
            spec_version: 1,
            prepare: None,
            markdown: None,
            embedding: None,
        };

        let value = serde_json::to_value(lock).expect("serialize tool lock");
        assert_eq!(value["spec_version"], 1);
    }

    #[test]
    fn tool_lock_hash_vector_matches_step2a() {
        let value = json!({
            "spec_version": 1,
            "prepare": {
                "tool_id": "prepare_default",
                "profile_hash": "sha256:20b67a9d7e7e2654379f16f20b445d007e95abac7c8f85d6da65beccff7e6b03",
                "kind": "deterministic_library"
            },
            "markdown": {
                "tool_id": "mistral_ocr_markdownize",
                "profile_hash": "sha256:24bd9e903241740fc9fe94fb72a6ff3e697b3c0859bd5aef1b49728a207e81ed",
                "kind": "online_api",
                "capabilities": ["ocr"],
                "url": "https://ignored.example"
            },
            "embedding": {
                "tool_id": "gemini_multimodal_embedding",
                "profile_hash": "sha256:c2bda78e217e1f9e12cd17ddac6c46e28a50b8060976f533f76f14193a807226",
                "dimensions": 1536,
                "distance": "cosine",
                "modality": "multimodal",
                "kind": "online_api",
                "mode": "ignored"
            },
            "summary": null,
            "classification": null,
            "rerank": null
        });

        assert_eq!(
            crate::identity::jcs_bytes(&canonical_tool_lock_value(&value).unwrap()).unwrap(),
            br#"{"embedding":{"dimensions":1536,"distance":"cosine","modality":"multimodal","profile_hash":"sha256:c2bda78e217e1f9e12cd17ddac6c46e28a50b8060976f533f76f14193a807226","tool_id":"gemini_multimodal_embedding"},"markdown":{"profile_hash":"sha256:24bd9e903241740fc9fe94fb72a6ff3e697b3c0859bd5aef1b49728a207e81ed","tool_id":"mistral_ocr_markdownize"},"prepare":{"profile_hash":"sha256:20b67a9d7e7e2654379f16f20b445d007e95abac7c8f85d6da65beccff7e6b03","tool_id":"prepare_default"},"spec_version":1}"#
        );
        assert_eq!(
            tool_lock_hash(&value).unwrap(),
            "sha256:e24d8b76742e441e894181f9210453e0da60a6e84c663560214d10aeeee0b264"
        );
    }

    #[test]
    fn tools_toml_auth_prefix_is_validated() {
        // R13-2: auth prefix validation now lives inside the typed loader and is
        // scoped to the `auth` field of a documented adapter role. (The old
        // `[tools.mistral]` grouping is no longer a recognized section — see
        // `r13_2_typed_loader_*` below.)
        validate_tools_toml(
            br#"[markdown.mistral_ocr_markdownize]
auth = "env:MISTRAL_API_KEY"
"#,
        )
        .unwrap();
        assert!(validate_tools_toml(
            br#"[markdown.mistral_ocr_markdownize]
auth = "file:/tmp/key"
"#
        )
        .is_err());
    }

    // R13-2(a): unknown sections/fields and type mismatches are exit-2 schema
    // errors, symmetric with config.toml (which rejected the same shapes while
    // tools.toml silently accepted them at exit 0).
    #[test]
    fn r13_2_typed_loader_rejects_unknown_key_and_type_mismatch() {
        // Unknown key directly under a role, with a scalar value (not a tool_id).
        assert!(validate_tools_toml(b"[markdown]\ntotally_bogus_key=\"xyz\"\n").is_err());
        // Type mismatch: cmd must be a string.
        assert!(validate_tools_toml(b"[markdown.x]\ncmd = 12345\n").is_err());
        // Unknown top-level section.
        assert!(validate_tools_toml(b"[tools.mistral]\nauth = \"env:X\"\n").is_err());
        // Unknown field inside a declared entry.
        assert!(validate_tools_toml(b"[embedding.g]\nbogus = \"y\"\n").is_err());
    }

    // Declared execution targets must match the built-in runtime. Target-rich
    // declarations are rejected until a matching dispatcher exists.
    #[test]
    fn declared_targets_must_match_builtin_runtime() {
        assert!(validate_tools_toml(
            br#"[markdown.mistral_ocr_markdownize]
kind = "online_api"
cmd = "uvx kcs-mistral-ocr-adapter"
model = "mistral-ocr-latest"
profile_hash = "sha256:..."
capabilities = ["ocr", "layout_detection", "table_extraction"]
"#,
        )
        .is_err());
        validate_tools_toml(
            br#"[markdown.mistral_ocr_markdownize]
kind = "online_api"
model = "mistral-ocr-latest"
auth = "env:MISTRAL_API_KEY"
"#,
        )
        .unwrap();
        validate_tools_toml(b"[embedding.gemini_embedding_2]\nauth = \"env:GEMINI_API_KEY\"\n")
            .unwrap();
        validate_tools_toml(b"[markdown]\nauth = \"plain:sk-secret-key\"\n").unwrap();
        assert!(validate_tools_toml(
            b"[embedding.custom]\nurl = \"https://example.test\"\nauth = \"plain:key\"\n"
        )
        .is_err());
    }

    #[test]
    fn auth_prefix_and_target_fields_are_validated_independently() {
        assert!(
            validate_tools_toml(b"[markdown.mistral_ocr_markdownize]\nurl = \"plain:\"\n").is_err()
        );
        assert!(validate_tools_toml(
            b"[markdown.mistral_ocr_markdownize]\nmodel = \"keychain:\"\n"
        )
        .is_err());
        assert!(validate_tools_toml(
            b"[markdown.mistral_ocr_markdownize]\nauth = \"file:/tmp/key\"\n"
        )
        .is_err());
    }

    // R13-2(2)/(e): auth resolution — env resolves, plain is literal, keychain is a
    // LOUD not-implemented error (never a silent noop).
    #[test]
    fn r13_2_resolve_auth_env_plain_and_keychain() {
        std::env::set_var("KCS_TEST_R13_2_AUTH", "resolved-key");
        assert_eq!(
            resolve_auth("env:KCS_TEST_R13_2_AUTH").unwrap(),
            Some("resolved-key".to_owned())
        );
        std::env::remove_var("KCS_TEST_R13_2_AUTH");
        assert_eq!(resolve_auth("env:KCS_TEST_R13_2_AUTH").unwrap(), None);
        assert_eq!(
            resolve_auth("plain:abc123").unwrap(),
            Some("abc123".to_owned())
        );
        assert!(matches!(
            resolve_auth("keychain:login"),
            Err(AdapterError::NotImplemented(_))
        ));
    }

    // R13-2(d): a declared `auth = "env:MY_KEY"` with MY_KEY set is honored (the
    // finding: it used to be ignored in favour of the hard-coded GEMINI_API_KEY).
    // (e): a declared `keychain:` is a LOUD not-implemented error, never a silent
    // noop. Absent a declaration, the legacy fallback env var is used.
    #[test]
    fn r13_2_resolve_declared_or_env_api_key_honors_declaration() {
        std::env::set_var("KCS_TEST_R13_2_DECLARED", "declared-key");
        let declared = DeclaredAdapter {
            tool_id: Some("gemini".to_owned()),
            model: None,
            auth: Some("env:KCS_TEST_R13_2_DECLARED".to_owned()),
            ..DeclaredAdapter::default()
        };
        assert_eq!(
            resolve_declared_or_env_api_key(Some(&declared), "GEMINI_API_KEY").unwrap(),
            Some("declared-key".to_owned())
        );
        std::env::remove_var("KCS_TEST_R13_2_DECLARED");

        // keychain → loud NotImplemented (e).
        let keychain = DeclaredAdapter {
            tool_id: None,
            model: None,
            auth: Some("keychain:login".to_owned()),
            ..DeclaredAdapter::default()
        };
        assert!(matches!(
            resolve_declared_or_env_api_key(Some(&keychain), "GEMINI_API_KEY"),
            Err(AdapterError::NotImplemented(_))
        ));

        // No declaration → the legacy env fallback.
        std::env::set_var("KCS_TEST_R13_2_FALLBACK", "fallback-key");
        assert_eq!(
            resolve_declared_or_env_api_key(None, "KCS_TEST_R13_2_FALLBACK").unwrap(),
            Some("fallback-key".to_owned())
        );
        std::env::remove_var("KCS_TEST_R13_2_FALLBACK");
    }

    #[test]
    fn r13_2_declared_adapter_for_role_reads_model_and_auth() {
        let value: toml::Value = toml::from_str(
            "[embedding.gemini_embedding_2]\nmodel = \"gemini-embedding-2\"\nauth = \"env:MY_KEY\"\n",
        )
        .unwrap();
        let declared = declared_adapter_for_role(&value, "embedding").unwrap();
        assert_eq!(declared.tool_id.as_deref(), Some("gemini_embedding_2"));
        assert_eq!(declared.model.as_deref(), Some("gemini-embedding-2"));
        assert_eq!(declared.auth.as_deref(), Some("env:MY_KEY"));
        // Single-adapter form (fields directly under the role).
        let flat: toml::Value = toml::from_str("[markdown]\nauth = \"plain:k\"\n").unwrap();
        let declared = declared_adapter_for_role(&flat, "markdown").unwrap();
        assert_eq!(declared.tool_id, None);
        assert_eq!(declared.auth.as_deref(), Some("plain:k"));
        assert_eq!(declared_adapter_for_role(&flat, "embedding"), None);
    }

    #[test]
    fn declared_adapter_projection_preserves_target_for_runtime_recheck() {
        let value: toml::Value = toml::from_str(
            "[embedding.custom]\nkind = \"online_api\"\nurl = \"https://example.test\"\nmodel = \"custom-v1\"\nauth = \"plain:synthetic\"\n",
        )
        .unwrap();
        let declared = declared_adapter_for_role(&value, "embedding").unwrap();
        assert_eq!(declared.tool_id.as_deref(), Some("custom"));
        assert_eq!(declared.url.as_deref(), Some("https://example.test"));
        assert!(validate_declared_runtime_target("embedding", &declared).is_err());
    }
}
