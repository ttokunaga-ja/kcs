//! Scan preview contracts.

use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};

use crate::prepare::hash_bytes;
use crate::{IoResultExt, Result};

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ScanCandidate {
    pub input_path: String,
    pub media_type: String,
    pub size_bytes: u64,
    pub raw_hash: Option<String>,
    pub ignored: bool,
    pub quarantine_reason: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ScanPreview {
    pub scope_id: String,
    pub candidates: Vec<ScanCandidate>,
    pub estimated_cost: Option<CostPreview>,
    pub approval_required: bool,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct CostPreview {
    pub estimated_usd: f64,
    pub budget_cap_usd: Option<f64>,
    pub budget_warning: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ScanPreviewRequest {
    pub scope_path: String,
    pub include_raw_hashes: bool,
    pub require_network_approval: bool,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SecretTier {
    TierA,
    TierB,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct IgnoreRule {
    pub pattern: String,
    pub negated: bool,
}

pub fn build_scan_preview(request: ScanPreviewRequest) -> Result<ScanPreview> {
    let scope_path = PathBuf::from(&request.scope_path);
    let mut ignore_rules = load_config_ignore(&scope_path)?;
    ignore_rules.extend(load_kcsignore(&scope_path)?);
    let mut candidates = Vec::new();
    collect_direct_candidates(
        &scope_path,
        &ignore_rules,
        request.include_raw_hashes,
        &mut candidates,
    )?;
    candidates.sort_by(|a, b| a.input_path.cmp(&b.input_path));
    let estimated_usd = candidates
        .iter()
        .filter(|candidate| !candidate.ignored)
        .map(|candidate| candidate.size_bytes as f64 / 1_000_000.0 * 0.01)
        .sum::<f64>();
    Ok(ScanPreview {
        scope_id: scope_id_from_scope_json(&scope_path).unwrap_or_else(|| "unknown".to_owned()),
        candidates,
        estimated_cost: Some(CostPreview {
            estimated_usd,
            budget_cap_usd: None,
            budget_warning: None,
        }),
        approval_required: request.require_network_approval,
    })
}

fn collect_direct_candidates(
    scope_path: &Path,
    ignore_rules: &[IgnoreRule],
    include_raw_hashes: bool,
    candidates: &mut Vec<ScanCandidate>,
) -> Result<()> {
    for entry in std::fs::read_dir(scope_path).pipeline_io(scope_path)? {
        let entry = entry.pipeline_io(scope_path)?;
        let name = match entry.file_name().into_string() {
            Ok(name) => name,
            Err(_) => continue,
        };
        if name == ".kcs" || name == ".kcsignore" {
            continue;
        }
        let path = entry.path();
        if is_xdg_state_inside_scope(scope_path, &path) {
            continue;
        }
        let file_type = entry.file_type().pipeline_io(&path)?;
        if !file_type.is_file() {
            continue;
        }
        let relative = path
            .strip_prefix(scope_path)
            .unwrap_or(&path)
            .to_string_lossy()
            .replace('\\', "/");
        if relative == ".kcsignore" {
            continue;
        }
        let size_bytes = entry.metadata().pipeline_io(&path)?.len();
        let secret = classify_secret(&relative);
        let ignored = ignored_by_rules(&relative, file_type.is_dir(), ignore_rules)
            || secret == Some(SecretTier::TierA)
                && !explicitly_unignored(&relative, file_type.is_dir(), ignore_rules);
        let quarantine_reason = match secret {
            Some(SecretTier::TierA) if ignored => Some("secrets_tier_a_excluded".to_owned()),
            Some(SecretTier::TierB) => Some("secrets_tier_b_warning".to_owned()),
            _ => None,
        };
        let raw_hash = if include_raw_hashes && !ignored {
            Some(hash_bytes(&std::fs::read(&path).pipeline_io(&path)?))
        } else {
            None
        };
        candidates.push(ScanCandidate {
            input_path: relative.clone(),
            media_type: media_type_for_path(&path).to_owned(),
            size_bytes,
            raw_hash,
            ignored,
            quarantine_reason,
        });
    }
    Ok(())
}

fn is_xdg_state_inside_scope(scope_path: &Path, path: &Path) -> bool {
    let scope_path = scope_path
        .canonicalize()
        .unwrap_or_else(|_| scope_path.to_path_buf());
    let path = path.canonicalize().unwrap_or_else(|_| path.to_path_buf());
    ["XDG_CONFIG_HOME", "XDG_DATA_HOME"]
        .iter()
        .filter_map(std::env::var_os)
        .map(PathBuf::from)
        .map(|path| path.canonicalize().unwrap_or(path))
        .filter(|xdg| xdg.starts_with(&scope_path))
        .any(|xdg| path == xdg || path.starts_with(&xdg))
}

pub fn load_kcsignore(scope_path: &Path) -> Result<Vec<IgnoreRule>> {
    let path = scope_path.join(".kcsignore");
    if !path.is_file() {
        return Ok(Vec::new());
    }
    let content = std::fs::read_to_string(&path).pipeline_io(&path)?;
    Ok(content
        .lines()
        .filter_map(|line| {
            let trimmed = line.trim();
            if trimmed.is_empty() || trimmed.starts_with('#') {
                return None;
            }
            let (negated, pattern) = trimmed
                .strip_prefix('!')
                .map(|pattern| (true, pattern))
                .unwrap_or((false, trimmed));
            Some(IgnoreRule {
                pattern: pattern.to_owned(),
                negated,
            })
        })
        .collect())
}

pub fn load_config_ignore(scope_path: &Path) -> Result<Vec<IgnoreRule>> {
    let path = scope_path.join(".kcs/config.toml");
    let text = match std::fs::read_to_string(&path) {
        Ok(text) => text,
        Err(err) if err.kind() == std::io::ErrorKind::NotFound => return Ok(Vec::new()),
        Err(err) => {
            return Err(crate::PipelineError::Io {
                path: path.display().to_string(),
                message: err.to_string(),
            });
        }
    };
    let value: toml::Value =
        toml::from_str(&text).map_err(|err| crate::PipelineError::Schema(err.to_string()))?;
    let Some(ignore) = value
        .get("scope")
        .and_then(|scope| scope.get("ignore"))
        .and_then(toml::Value::as_array)
    else {
        return Ok(Vec::new());
    };
    Ok(ignore
        .iter()
        .filter_map(toml::Value::as_str)
        .map(|pattern| IgnoreRule {
            pattern: pattern.trim_start_matches('!').to_owned(),
            negated: pattern.starts_with('!'),
        })
        .collect())
}

#[must_use]
pub fn classify_secret(path: &str) -> Option<SecretTier> {
    let normalized = path.trim_start_matches('/').replace('\\', "/");
    let name = normalized.rsplit('/').next().unwrap_or(&normalized);
    let lower = name.to_ascii_lowercase();
    let lower_path = normalized.to_ascii_lowercase();
    let tier_a_path = lower_path == ".kube/config"
        || lower_path == ".docker/config.json"
        || lower_path.starts_with(".ssh/")
        || lower_path.starts_with(".gnupg/")
        || lower_path.starts_with(".aws/")
        || lower_path.starts_with(".kube/")
        || lower_path.starts_with(".docker/");
    let tier_a = lower == ".env"
        || lower.starts_with(".env.")
        || lower == ".ssh"
        || lower == ".gnupg"
        || lower == ".aws"
        || lower == ".kube"
        || lower == ".docker"
        || lower.ends_with(".pem")
        || lower.ends_with(".key")
        || lower.ends_with(".p12")
        || lower.ends_with(".pfx")
        || lower.starts_with("id_rsa")
        || lower.starts_with("id_ecdsa")
        || lower.starts_with("id_ed25519")
        || lower.ends_with(".keystore")
        || lower == ".netrc"
        || lower == ".npmrc"
        || lower == ".pypirc"
        || lower.ends_with(".tfstate")
        || lower.contains(".tfstate.")
        || tier_a_path;
    if tier_a {
        return Some(SecretTier::TierA);
    }
    let tier_b = ["credentials", "secret", "token", "apikey", "password"]
        .iter()
        .any(|needle| lower.contains(needle));
    tier_b.then_some(SecretTier::TierB)
}

#[must_use]
pub fn ignored_by_rules(path: &str, is_dir: bool, rules: &[IgnoreRule]) -> bool {
    let mut ignored = false;
    for rule in rules {
        if matches_ignore_pattern(path, is_dir, &rule.pattern) {
            ignored = !rule.negated;
        }
    }
    ignored
}

fn explicitly_unignored(path: &str, is_dir: bool, rules: &[IgnoreRule]) -> bool {
    rules
        .iter()
        .any(|rule| rule.negated && matches_ignore_pattern(path, is_dir, &rule.pattern))
}

fn matches_ignore_pattern(path: &str, is_dir: bool, pattern: &str) -> bool {
    let directory_only = pattern.ends_with('/');
    if directory_only && !is_dir {
        return false;
    }
    let rooted = pattern.starts_with('/');
    let pattern = pattern.trim_start_matches('/').trim_end_matches('/');
    let normalized_path = path.trim_start_matches('/').replace('\\', "/");
    if !rooted && !pattern.contains('/') {
        return wildcard_match(
            pattern,
            normalized_path
                .rsplit('/')
                .next()
                .unwrap_or(&normalized_path),
        );
    }
    wildcard_match(pattern, &normalized_path)
}

fn wildcard_match(pattern: &str, value: &str) -> bool {
    wildcard_match_bytes(pattern.as_bytes(), value.as_bytes())
}

fn wildcard_match_bytes(pattern: &[u8], value: &[u8]) -> bool {
    if pattern.is_empty() {
        return value.is_empty();
    }
    if pattern.starts_with(b"**/") {
        return wildcard_match_bytes(&pattern[3..], value)
            || value
                .iter()
                .position(|byte| *byte == b'/')
                .map(|slash| wildcard_match_bytes(pattern, &value[slash + 1..]))
                .unwrap_or(false);
    }
    if pattern == b"**" {
        return true;
    }
    match pattern[0] {
        b'*' => {
            wildcard_match_bytes(&pattern[1..], value)
                || !value.is_empty()
                    && value[0] != b'/'
                    && wildcard_match_bytes(pattern, &value[1..])
        }
        b'?' => {
            !value.is_empty()
                && value[0] != b'/'
                && wildcard_match_bytes(&pattern[1..], &value[1..])
        }
        byte => {
            !value.is_empty()
                && byte == value[0]
                && wildcard_match_bytes(&pattern[1..], &value[1..])
        }
    }
}

fn media_type_for_path(path: &Path) -> &'static str {
    match path
        .extension()
        .and_then(|ext| ext.to_str())
        .unwrap_or_default()
    {
        "md" | "markdown" => "text/markdown",
        "txt" => "text/plain",
        "rs" | "py" | "js" | "ts" | "go" | "java" | "c" | "h" | "cpp" => "text/x-code",
        "pdf" => "application/pdf",
        "png" => "image/png",
        "jpg" | "jpeg" => "image/jpeg",
        _ => "application/octet-stream",
    }
}

fn scope_id_from_scope_json(scope_path: &Path) -> Option<String> {
    let value = std::fs::read_to_string(scope_path.join(".kcs/scope.json")).ok()?;
    let value = serde_json::from_str::<serde_json::Value>(&value).ok()?;
    value.get("scope_id")?.as_str().map(str::to_owned)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn placeholder_scan_candidate_serializes() {
        let candidate = ScanCandidate {
            input_path: "report.pdf".to_owned(),
            media_type: "application/pdf".to_owned(),
            size_bytes: 42,
            raw_hash: None,
            ignored: false,
            quarantine_reason: None,
        };

        let value = serde_json::to_value(candidate).expect("serialize scan candidate");
        assert_eq!(value["input_path"], "report.pdf");
    }

    #[test]
    fn secrets_and_ignore_rules_are_applied_in_order() {
        let rules = vec![
            IgnoreRule {
                pattern: "*.log".to_owned(),
                negated: false,
            },
            IgnoreRule {
                pattern: "keep.log".to_owned(),
                negated: true,
            },
        ];
        assert_eq!(classify_secret(".env"), Some(SecretTier::TierA));
        assert_eq!(classify_secret("api_token.txt"), Some(SecretTier::TierB));
        assert!(ignored_by_rules("debug.log", false, &rules));
        assert!(!ignored_by_rules("keep.log", false, &rules));
    }
}
