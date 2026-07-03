//! Evidence Pointer contracts.

use serde::{Deserialize, Serialize};

use crate::{Result, SearchError};

pub const EVIDENCE_POINTER_SCHEMA_VERSION: u64 = 1;

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct EvidencePointer {
    pub schema_version: u64,
    pub commit: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tree: Option<String>,
    pub raw_hash: String,
    pub tool_profile_hash: String,
    pub chunk_hash: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub path_at_commit: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub heading_path: Option<Vec<String>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub section_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub char_start: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub char_end: Option<u64>,
    pub scope_id: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub scope_path: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct EvidencePointerIssueRequest {
    pub scope_id: String,
    pub scope_path: Option<String>,
    pub commit: String,
    pub tree: Option<String>,
    pub raw_hash: String,
    pub tool_profile_hash: String,
    pub chunk_hash: String,
    pub path_at_commit: Option<String>,
    pub heading_path: Option<Vec<String>>,
    pub section_id: Option<String>,
    pub char_start: Option<u64>,
    pub char_end: Option<u64>,
}

pub fn issue_evidence_pointer(request: EvidencePointerIssueRequest) -> Result<EvidencePointer> {
    Ok(EvidencePointer {
        schema_version: EVIDENCE_POINTER_SCHEMA_VERSION,
        commit: request.commit,
        tree: request.tree,
        raw_hash: request.raw_hash,
        tool_profile_hash: request.tool_profile_hash,
        chunk_hash: request.chunk_hash,
        path_at_commit: request.path_at_commit,
        heading_path: request.heading_path,
        section_id: request.section_id,
        char_start: request.char_start,
        char_end: request.char_end,
        scope_id: request.scope_id,
        scope_path: request.scope_path,
    })
}

pub fn evidence_pointer_to_uri(pointer: &EvidencePointer) -> Result<String> {
    if pointer.schema_version != EVIDENCE_POINTER_SCHEMA_VERSION {
        return Err(SearchError::Evidence(
            "unsupported evidence schema version".to_owned(),
        ));
    }
    Ok(format!(
        "kcs://{}/{}/{}/{}/{}",
        pointer.scope_id,
        pointer.commit,
        pointer.raw_hash,
        pointer.tool_profile_hash,
        pointer.chunk_hash
    ))
}

pub fn parse_evidence_pointer_uri(uri: &str) -> Result<EvidencePointer> {
    let rest = uri
        .strip_prefix("kcs://")
        .ok_or_else(|| SearchError::Evidence("evidence URI must start with kcs://".to_owned()))?;
    let (path, query) = rest.split_once('?').unwrap_or((rest, ""));
    let schema_version = if query.is_empty() {
        EVIDENCE_POINTER_SCHEMA_VERSION
    } else {
        let mut version = EVIDENCE_POINTER_SCHEMA_VERSION;
        for part in query.split('&') {
            if let Some(value) = part.strip_prefix("sv=") {
                version = value.parse::<u64>().map_err(|_| {
                    SearchError::Evidence("invalid evidence schema version".to_owned())
                })?;
            }
        }
        version
    };
    if schema_version != EVIDENCE_POINTER_SCHEMA_VERSION {
        return Err(SearchError::Evidence(
            "KCS-E-CONFIG-SCHEMA-001: unsupported evidence schema version".to_owned(),
        ));
    }
    let parts = path.split('/').collect::<Vec<_>>();
    if parts.len() == 3 && parts.get(1) == Some(&"object") {
        return Err(SearchError::Evidence(
            "object reference URI is not an evidence pointer".to_owned(),
        ));
    }
    if parts.len() != 5 {
        return Err(SearchError::Evidence(
            "evidence URI must have five path segments".to_owned(),
        ));
    }
    Ok(EvidencePointer {
        schema_version,
        scope_id: parts[0].to_owned(),
        commit: parts[1].to_owned(),
        raw_hash: parts[2].to_owned(),
        tool_profile_hash: parts[3].to_owned(),
        chunk_hash: parts[4].to_owned(),
        tree: None,
        path_at_commit: None,
        heading_path: None,
        section_id: None,
        char_start: None,
        char_end: None,
        scope_path: None,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn pointer() -> EvidencePointer {
        EvidencePointer {
            schema_version: 1,
            commit: "sha256:9f2c1a7b04dee5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e"
                .to_owned(),
            tree: Some("sha256:tree".to_owned()),
            raw_hash: "sha256:74bcb92d8088c950e45e4c43563332da2ca1e04b25d6d4016aa43f830d4cca8a"
                .to_owned(),
            tool_profile_hash:
                "sha256:e067e42e6634b8043f46a4b7f55257ab10ca6266be80cc47b6a68a5aacd2c8f0".to_owned(),
            chunk_hash: "sha256:c5e31f10da04b722769bdbbd60a55b94c177b5f3bf9c64e5341be7281d115c3d"
                .to_owned(),
            path_at_commit: Some("report.pdf".to_owned()),
            heading_path: Some(vec!["認証仕様".to_owned(), "API Token".to_owned()]),
            section_id: Some("認証仕様/api-token".to_owned()),
            char_start: Some(1200),
            char_end: Some(1500),
            scope_id: "scope_01J8ZQABCDEFGHJKMNPQRS".to_owned(),
            scope_path: Some("/tmp/scope".to_owned()),
        }
    }

    #[test]
    fn ct3_evidence_001_issue_pointer_has_required_fields_and_uri() {
        let pointer = pointer();
        let uri = evidence_pointer_to_uri(&pointer).unwrap();
        assert!(uri.starts_with("kcs://scope_01J8ZQ"));
        assert_eq!(pointer.schema_version, 1);
        assert!(pointer.heading_path.is_some());
        assert!(pointer.char_start.is_some());
    }

    #[test]
    fn ct3_uri_001_json_uri_json_roundtrip_drops_only_optional_fields() {
        let uri = evidence_pointer_to_uri(&pointer()).unwrap();
        assert_eq!(
            uri,
            "kcs://scope_01J8ZQABCDEFGHJKMNPQRS/sha256:9f2c1a7b04dee5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e/sha256:74bcb92d8088c950e45e4c43563332da2ca1e04b25d6d4016aa43f830d4cca8a/sha256:e067e42e6634b8043f46a4b7f55257ab10ca6266be80cc47b6a68a5aacd2c8f0/sha256:c5e31f10da04b722769bdbbd60a55b94c177b5f3bf9c64e5341be7281d115c3d"
        );
        let parsed = parse_evidence_pointer_uri(&uri).unwrap();
        assert_eq!(parsed.scope_id, pointer().scope_id);
        assert!(parsed.heading_path.is_none());
    }

    #[test]
    fn ct3_uri_002_object_reference_is_distinct_from_evidence_pointer() {
        assert!(parse_evidence_pointer_uri("kcs://scope/object/image/sha256:abc").is_err());
    }

    #[test]
    fn ct3_uri_004_sv_default_and_unknown_sv_rejected() {
        let uri = evidence_pointer_to_uri(&pointer()).unwrap();
        assert_eq!(parse_evidence_pointer_uri(&uri).unwrap().schema_version, 1);
        assert!(parse_evidence_pointer_uri(&(uri + "?sv=99")).is_err());
    }
}
