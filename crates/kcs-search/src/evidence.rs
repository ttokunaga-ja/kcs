//! Evidence Pointer contracts.

use serde::{Deserialize, Serialize};

use crate::Result;

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

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum EvidenceResolutionKind {
    RawObject,
    NormalizedUnit,
    ChunkText,
    Tombstone,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct EvidenceResolution {
    pub pointer: EvidencePointer,
    pub kind: EvidenceResolutionKind,
    pub commit_shallow: bool,
    pub content_hash: Option<String>,
    pub text: Option<String>,
}

pub trait EvidencePointerIssuer {
    fn issue_pointer(&self, request: EvidencePointerIssueRequest) -> Result<EvidencePointer>;
}

pub trait EvidenceResolver {
    fn resolve_pointer(&self, pointer: &EvidencePointer) -> Result<EvidenceResolution>;
}

pub fn issue_evidence_pointer(_request: EvidencePointerIssueRequest) -> Result<EvidencePointer> {
    todo!("Step 3c will issue Evidence Pointers from search results")
}

pub fn resolve_evidence_pointer(_pointer: &EvidencePointer) -> Result<EvidenceResolution> {
    todo!("Step 3c will resolve Evidence Pointers through scope and object stores")
}

pub fn evidence_pointer_to_uri(_pointer: &EvidencePointer) -> Result<String> {
    todo!("Step 3c will serialize Evidence Pointer URI form")
}

pub fn parse_evidence_pointer_uri(_uri: &str) -> Result<EvidencePointer> {
    todo!("Step 3c will parse Evidence Pointer URI form")
}
