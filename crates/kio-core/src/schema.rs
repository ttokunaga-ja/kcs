use serde_json::Value;

use crate::error::{KioError, Result};

#[derive(Debug, Clone, Copy)]
pub enum SchemaKind {
    Config,
    Scope,
    Manifest,
}

impl SchemaKind {
    const fn name(self) -> &'static str {
        match self {
            Self::Config => "config.toml",
            Self::Scope => "scope.json",
            Self::Manifest => "manifest.json",
        }
    }

    const fn schema_text(self) -> &'static str {
        match self {
            Self::Config => include_str!("../schemas/config.schema.json"),
            Self::Scope => include_str!("../schemas/scope.schema.json"),
            Self::Manifest => include_str!("../schemas/manifest.schema.json"),
        }
    }
}

pub fn validate_json_schema(kind: SchemaKind, value: &Value) -> Result<()> {
    let schema: Value = serde_json::from_str(kind.schema_text())
        .map_err(|err| KioError::schema(err.to_string()))?;
    let validator =
        jsonschema::validator_for(&schema).map_err(|err| KioError::schema(err.to_string()))?;
    validator
        .validate(value)
        .map_err(|err| KioError::schema(format!("{}: {err}", kind.name())))
}
