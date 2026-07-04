//! Cursor token contracts for deterministic paging.

use base64::engine::general_purpose::URL_SAFE_NO_PAD;
use base64::Engine;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

use crate::{Result, SearchError};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ScopeMode {
    All,
    Scope,
    Descendants,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ScopeCursor {
    pub scope_id: String,
    pub snapshot_commit: String,
    pub max_rowid: u64,
    pub consumed: u64,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct CursorToken {
    #[serde(rename = "v")]
    pub version: u64,
    pub scope_mode: ScopeMode,
    pub query_hash: String,
    pub scopes: Vec<ScopeCursor>,
}

/// Serialize + HMAC-sign a cursor into `<base64url(JCS)>.<base64url(HMAC-SHA256)>`
/// (O1(b)). The signature is computed over the canonical JCS bytes with a
/// device-local key so a caller cannot forge or tamper a token to jump scope or
/// page — `query_hash` alone binds only public inputs. The inner payload stays
/// exactly the previous `base64url(JCS(token))`, so the wire form is still
/// URL-safe and pad-free; only the `.signature` suffix is new.
pub fn encode_cursor_token(token: &CursorToken, key: &[u8]) -> Result<String> {
    let value = serde_json::to_value(token).map_err(|err| SearchError::Cursor(err.to_string()))?;
    let bytes = serde_jcs::to_vec(&value).map_err(|err| SearchError::Cursor(err.to_string()))?;
    let signature = hmac_sha256(key, &bytes);
    Ok(format!(
        "{}.{}",
        URL_SAFE_NO_PAD.encode(&bytes),
        URL_SAFE_NO_PAD.encode(signature)
    ))
}

/// Verify the HMAC signature, then decode the cursor. A missing or mismatched
/// signature is `SearchError::Cursor` (the CLI maps it to
/// `KCS-E-SEARCH-CURSOR-001`), so a forged / tampered token is rejected before
/// its frozen scope set is ever trusted.
pub fn decode_cursor_token(token: &str, key: &[u8]) -> Result<CursorToken> {
    let (payload_b64, signature_b64) = token
        .rsplit_once('.')
        .ok_or_else(|| SearchError::Cursor("cursor is missing its signature".to_owned()))?;
    let payload = URL_SAFE_NO_PAD
        .decode(payload_b64)
        .map_err(|err| SearchError::Cursor(err.to_string()))?;
    let provided = URL_SAFE_NO_PAD
        .decode(signature_b64)
        .map_err(|err| SearchError::Cursor(err.to_string()))?;
    let expected = hmac_sha256(key, &payload);
    if !constant_time_eq(&expected, &provided) {
        return Err(SearchError::Cursor("cursor signature mismatch".to_owned()));
    }
    serde_json::from_slice(&payload).map_err(|err| SearchError::Cursor(err.to_string()))
}

/// HMAC-SHA256 (RFC 2104) over `sha2`, avoiding a new dependency. Block size is
/// 64 bytes (SHA-256).
fn hmac_sha256(key: &[u8], message: &[u8]) -> [u8; 32] {
    const BLOCK: usize = 64;
    let mut block_key = [0u8; BLOCK];
    if key.len() > BLOCK {
        block_key[..32].copy_from_slice(&Sha256::digest(key));
    } else {
        block_key[..key.len()].copy_from_slice(key);
    }
    let mut ipad = [0x36u8; BLOCK];
    let mut opad = [0x5cu8; BLOCK];
    for i in 0..BLOCK {
        ipad[i] ^= block_key[i];
        opad[i] ^= block_key[i];
    }
    let mut inner = Sha256::new();
    inner.update(ipad);
    inner.update(message);
    let inner_digest = inner.finalize();
    let mut outer = Sha256::new();
    outer.update(opad);
    outer.update(inner_digest);
    outer.finalize().into()
}

/// Length-independent, branch-flat equality so signature verification does not
/// leak timing information about the expected MAC.
fn constant_time_eq(a: &[u8], b: &[u8]) -> bool {
    if a.len() != b.len() {
        return false;
    }
    let mut diff = 0u8;
    for (x, y) in a.iter().zip(b.iter()) {
        diff |= x ^ y;
    }
    diff == 0
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sample_token() -> CursorToken {
        CursorToken {
            version: 1,
            scope_mode: ScopeMode::All,
            query_hash: "sha256:query".to_owned(),
            scopes: vec![ScopeCursor {
                scope_id: "scope_01".to_owned(),
                snapshot_commit: "sha256:commit".to_owned(),
                max_rowid: 42,
                consumed: 20,
            }],
        }
    }

    #[test]
    fn ct3_cursor_004_cursor_is_base64url_jcs_json() {
        let token = sample_token();
        let key = b"cursor-round-trip-key";
        let encoded = encode_cursor_token(&token, key).unwrap();
        assert_eq!(decode_cursor_token(&encoded, key).unwrap(), token);
        assert!(!encoded.contains('='));
    }

    #[test]
    fn o1_tampered_or_mis_keyed_cursor_is_rejected() {
        let token = sample_token();
        let key = b"device-key-a";
        let encoded = encode_cursor_token(&token, key).unwrap();
        // A different device key fails signature verification.
        assert!(decode_cursor_token(&encoded, b"device-key-b").is_err());
        // Flipping a payload character (forging a scope jump) also fails.
        let (payload, signature) = encoded.rsplit_once('.').unwrap();
        let mut forged = payload.to_owned();
        let last = forged.pop().unwrap();
        forged.push(if last == 'A' { 'B' } else { 'A' });
        let forged = format!("{forged}.{signature}");
        assert!(decode_cursor_token(&forged, key).is_err());
    }
}
