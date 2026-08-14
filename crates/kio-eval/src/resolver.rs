//! Reconstruct current and historical fixture identities from strict manifests.

use std::collections::{HashMap, HashSet};

use kio_index::chunking::slugify_heading;
use thiserror::Error;

use crate::{
    ResultKey,
    manifest::{
        CorpusManifest, Expected, GoldenQuery, HistoryOperation, Scenario, frozen_history_plan,
    },
};

#[derive(Debug, Error, Clone, PartialEq, Eq)]
pub enum ResolveError {
    #[error("file is absent from the anchor manifest: {scope}/{file}")]
    NotAnchor { scope: String, file: String },
    #[error("raw_sha256 is absent: {scope}/{file}")]
    MissingRawHash { scope: String, file: String },
    #[error("section mnemonic {section:?} cannot be resolved for {scope}/{file}")]
    MissingSection {
        scope: String,
        file: String,
        section: String,
    },
    #[error("slugify resulted in an empty section for {scope}/{file}#{section}")]
    EmptySlug {
        scope: String,
        file: String,
        section: String,
    },
}

#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct FileTags {
    pub current: bool,
    pub renamed_from: bool,
    pub edited: bool,
    pub deleted: bool,
    pub original: bool,
}

impl FileTags {
    #[must_use]
    pub fn labels(&self) -> Vec<&'static str> {
        let mut labels = Vec::new();
        if self.current {
            labels.push("current");
        }
        if self.renamed_from {
            labels.push("renamed_from");
        }
        if self.edited {
            labels.push("edited");
        }
        if self.deleted {
            labels.push("deleted");
        }
        if self.original {
            labels.push("original");
        }
        labels
    }
}

/// Structural view used by dry-run checks. It intentionally contains neither
/// filesystem paths nor the live CAS: manifests are the only authority here.
#[derive(Debug, Clone)]
pub struct CorpusModel {
    sections: HashMap<(String, String), HashSet<String>>,
    original: HashSet<(String, String)>,
    renames_old: HashSet<(String, String)>,
    rename_new_to_old: HashMap<(String, String), (String, String)>,
    deleted: HashSet<(String, String)>,
    edited: HashSet<(String, String)>,
    current: HashSet<(String, String)>,
}

impl CorpusModel {
    #[must_use]
    pub fn new(corpus: &CorpusManifest) -> Self {
        let mut sections = HashMap::new();
        let mut original = HashSet::new();
        for entry in &corpus.files {
            let key = (entry.scope.clone(), entry.file.clone());
            original.insert(key.clone());
            sections.insert(
                key,
                entry
                    .sections
                    .iter()
                    .map(|section| section.slug.clone())
                    .collect(),
            );
        }
        let mut renames_old = HashSet::new();
        let mut renames_new = HashSet::new();
        let mut rename_new_to_old = HashMap::new();
        let plan = frozen_history_plan().expect("bundled history plan is validated at build time");
        let mut deleted = HashSet::new();
        let mut edited = HashSet::new();
        for operation in &plan.operations {
            match operation {
                HistoryOperation::Rename {
                    scope,
                    old_file,
                    new_file,
                    ..
                } => {
                    let old = (scope.clone(), old_file.clone());
                    let new = (scope.clone(), new_file.clone());
                    renames_old.insert(old.clone());
                    renames_new.insert(new.clone());
                    rename_new_to_old.insert(new, old);
                }
                HistoryOperation::Edit { scope, file, .. } => {
                    edited.insert((scope.clone(), file.clone()));
                }
                HistoryOperation::Delete { scope, file, .. } => {
                    deleted.insert((scope.clone(), file.clone()));
                }
            }
        }
        let current = original
            .difference(&renames_old)
            .filter(|key| !deleted.contains(*key))
            .cloned()
            .chain(renames_new.iter().cloned())
            .collect();
        Self {
            sections,
            original,
            renames_old,
            rename_new_to_old,
            deleted,
            edited,
            current,
        }
    }

    #[must_use]
    pub fn sections_of(&self, scope: &str, file: &str) -> Option<&HashSet<String>> {
        let key = (scope.to_owned(), file.to_owned());
        self.sections.get(&key).or_else(|| {
            self.rename_new_to_old
                .get(&key)
                .and_then(|old| self.sections.get(old))
        })
    }

    #[must_use]
    pub fn classify(&self, scope: &str, file: &str) -> FileTags {
        let key = (scope.to_owned(), file.to_owned());
        FileTags {
            current: self.current.contains(&key),
            renamed_from: self.renames_old.contains(&key),
            edited: self.edited.contains(&key),
            deleted: self.deleted.contains(&key),
            original: self.original.contains(&key),
        }
    }

    #[must_use]
    pub fn is_known_file(&self, scope: &str, file: &str) -> bool {
        self.sections_of(scope, file).is_some()
    }
}

#[derive(Debug, Clone)]
struct AnchorInfo {
    raw_sha256: String,
    sections: HashMap<String, String>,
}

/// Resolves golden mnemonic references to the evaluator's three-element
/// projection: `(raw_hash, section leaf, path_at_commit)`.
#[derive(Debug, Clone)]
pub struct Resolver {
    by_key: HashMap<(String, String), AnchorInfo>,
}

impl Resolver {
    #[must_use]
    pub fn new(corpus: &CorpusManifest) -> Self {
        let mut by_key = HashMap::new();
        for entry in corpus.files.iter().filter(|entry| entry.anchor) {
            by_key.insert(
                (entry.scope.clone(), entry.file.clone()),
                AnchorInfo {
                    raw_sha256: entry.raw_sha256.clone(),
                    sections: entry
                        .sections
                        .iter()
                        .map(|section| (section.slug.clone(), section.heading.clone()))
                        .collect(),
                },
            );
        }
        // Historical identities are derived exclusively from the frozen plan,
        // never duplicated in execution evidence.
        let plan = frozen_history_plan().expect("bundled history plan is validated at build time");
        for operation in &plan.operations {
            match operation {
                HistoryOperation::Edit {
                    scope,
                    file,
                    before_raw_sha256,
                    sections,
                    ..
                }
                | HistoryOperation::Delete {
                    scope,
                    file,
                    before_raw_sha256,
                    sections,
                } => {
                    Self::overlay(&mut by_key, scope, file, before_raw_sha256, sections);
                }
                HistoryOperation::Rename {
                    scope,
                    old_file,
                    before_raw_sha256,
                    sections,
                    ..
                } => {
                    Self::overlay(&mut by_key, scope, old_file, before_raw_sha256, sections);
                }
            }
        }
        Self { by_key }
    }

    fn overlay(
        by_key: &mut HashMap<(String, String), AnchorInfo>,
        scope: &str,
        file: &str,
        raw_sha256: &str,
        sections: &[crate::manifest::Section],
    ) {
        let key = (scope.to_owned(), file.to_owned());
        let raw_sha256 = raw_sha256.to_owned();
        let resolved_sections = sections
            .iter()
            .map(|section| (section.slug.clone(), section.heading.clone()))
            .collect();
        by_key.insert(
            key,
            AnchorInfo {
                raw_sha256,
                sections: resolved_sections,
            },
        );
    }

    pub fn resolve_one(
        &self,
        scope: &str,
        file: &str,
        mnemonic: &str,
    ) -> Result<ResultKey, ResolveError> {
        let Some(info) = self.by_key.get(&(scope.to_owned(), file.to_owned())) else {
            return Err(ResolveError::NotAnchor {
                scope: scope.to_owned(),
                file: file.to_owned(),
            });
        };
        if info.raw_sha256.is_empty() {
            return Err(ResolveError::MissingRawHash {
                scope: scope.to_owned(),
                file: file.to_owned(),
            });
        }
        let Some(heading) = info.sections.get(mnemonic) else {
            return Err(ResolveError::MissingSection {
                scope: scope.to_owned(),
                file: file.to_owned(),
                section: mnemonic.to_owned(),
            });
        };
        let section = slugify_heading(heading);
        if section.is_empty() {
            return Err(ResolveError::EmptySlug {
                scope: scope.to_owned(),
                file: file.to_owned(),
                section: mnemonic.to_owned(),
            });
        }
        Ok((
            format!("sha256:{}", info.raw_sha256),
            Some(section),
            Some(file.to_owned()),
        ))
    }

    pub fn resolve_expected(
        &self,
        expected: &[Expected],
    ) -> (HashSet<ResultKey>, Vec<ResolveError>) {
        let mut resolved = HashSet::new();
        let mut errors = Vec::new();
        for item in expected {
            match self.resolve_one(&item.scope, &item.file, &item.section) {
                Ok(key) => {
                    resolved.insert(key);
                }
                Err(error) => errors.push(error),
            }
        }
        (resolved, errors)
    }
}

/// Return every dry-run inconsistency for a query; callers may aggregate these
/// without losing later problems after the first malformed expected item.
#[must_use]
pub fn validate_query(
    query: &GoldenQuery,
    model: &CorpusModel,
    resolver: &Resolver,
) -> Vec<String> {
    let mut problems = Vec::new();
    for expected in &query.expected {
        let Some(sections) = model.sections_of(&expected.scope, &expected.file) else {
            problems.push(format!(
                "file absent from corpus: {}/{}",
                expected.scope, expected.file
            ));
            continue;
        };
        if !sections.contains(&expected.section) {
            problems.push(format!(
                "section absent: {}/{}#{}",
                expected.scope, expected.file, expected.section
            ));
        }
        let tags = model.classify(&expected.scope, &expected.file);
        match query.scenario {
            Scenario::M3_1 if !tags.current || tags.renamed_from || tags.deleted => {
                problems.push(format!(
                    "M3-1 requires a current file: {}/{} tags={:?}",
                    expected.scope,
                    expected.file,
                    tags.labels()
                ))
            }
            Scenario::M3_2 if !tags.renamed_from && !tags.edited => problems.push(format!(
                "M3-2 requires historical renamed_from/edited file: {}/{} tags={:?}",
                expected.scope,
                expected.file,
                tags.labels()
            )),
            Scenario::M3_3 if !tags.deleted => problems.push(format!(
                "M3-3 requires deleted file: {}/{} tags={:?}",
                expected.scope,
                expected.file,
                tags.labels()
            )),
            _ => {}
        }
    }
    let (_, errors) = resolver.resolve_expected(&query.expected);
    problems.extend(errors.into_iter().map(|error| error.to_string()));
    problems
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::manifest::{CorpusFile, Section};

    fn corpus() -> CorpusManifest {
        CorpusManifest {
            generator: "kio-eval generate-corpus".into(),
            seed: 20_260_703,
            scopes: vec![],
            file_count: 0,
            anchor_count: 0,
            files: vec![CorpusFile {
                scope: "research".into(),
                file: "gone.md".into(),
                kind: "md".into(),
                anchor: true,
                role: "m3_3_delete".into(),
                sections: vec![Section {
                    slug: "fact".into(),
                    heading: "Fact Heading".into(),
                }],
                raw_sha256: "a".repeat(64),
            }],
        }
    }
    #[test]
    fn overlays_old_content_and_resolves_three_tuple() {
        let resolver = Resolver::new(&corpus());
        assert_eq!(
            resolver.resolve_one("research", "gone.md", "fact").unwrap(),
            (
                format!("sha256:{}", "a".repeat(64)),
                Some("fact-heading".into()),
                Some("gone.md".into())
            )
        );
    }
}
