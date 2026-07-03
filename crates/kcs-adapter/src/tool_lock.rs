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

pub fn validate_tools_toml_value(value: &toml::Value) -> Result<()> {
    validate_auth_fields(value)
}

fn validate_tool_lock_value(value: &Value) -> Result<()> {
    let object = value
        .as_object()
        .ok_or_else(|| AdapterError::ConfigSchema("tool-lock.json must be an object".to_owned()))?;
    if object.get("spec_version").and_then(Value::as_u64).is_none() {
        return Err(AdapterError::ConfigSchema(
            "tool-lock.json spec_version must be an integer".to_owned(),
        ));
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

fn validate_auth_fields(value: &toml::Value) -> Result<()> {
    match value {
        toml::Value::String(string) => {
            if looks_like_auth_value(string) && !valid_auth_value(string) {
                return Err(AdapterError::ConfigSchema(
                    "auth must start with keychain:, env:, or plain:".to_owned(),
                ));
            }
        }
        toml::Value::Array(values) => {
            for value in values {
                validate_auth_fields(value)?;
            }
        }
        toml::Value::Table(table) => {
            for (key, value) in table {
                if key == "auth" {
                    let Some(auth) = value.as_str() else {
                        return Err(AdapterError::ConfigSchema(
                            "auth must be a string".to_owned(),
                        ));
                    };
                    if !valid_auth_value(auth) {
                        return Err(AdapterError::ConfigSchema(
                            "auth must start with keychain:, env:, or plain:".to_owned(),
                        ));
                    }
                } else {
                    validate_auth_fields(value)?;
                }
            }
        }
        toml::Value::Integer(_)
        | toml::Value::Float(_)
        | toml::Value::Boolean(_)
        | toml::Value::Datetime(_) => {}
    }
    Ok(())
}

fn looks_like_auth_value(value: &str) -> bool {
    value.contains(':')
        && ["keychain:", "env:", "plain:"]
            .iter()
            .any(|prefix| value.starts_with(prefix))
}

fn valid_auth_value(value: &str) -> bool {
    ["keychain:", "env:", "plain:"]
        .iter()
        .any(|prefix| value.starts_with(prefix) && value.len() > prefix.len())
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
        validate_tools_toml(
            br#"[tools.mistral]
auth = "env:MISTRAL_API_KEY"
"#,
        )
        .unwrap();
        assert!(validate_tools_toml(
            br#"[tools.mistral]
auth = "file:/tmp/key"
"#
        )
        .is_err());
    }
}
