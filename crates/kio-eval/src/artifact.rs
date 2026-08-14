//! Create-only publication for evaluator evidence artifacts.

use std::{
    ffi::OsString,
    fs,
    io::Write,
    path::{Path, PathBuf},
};

use cap_primitives::{ambient_authority, fs as cap_fs};
use thiserror::Error;

use crate::boundary::same_directory_identity;

#[derive(Debug, Error)]
#[error("{0}")]
pub struct ArtifactError(String);

/// A retained output parent and an absent final leaf outside the measured
/// input root. Evidence commands never overwrite an earlier measurement.
pub struct CreateOnlyArtifact {
    parent: fs::File,
    parent_path: PathBuf,
    parent_identity: fs::Metadata,
    name: OsString,
    public_path: PathBuf,
    label: &'static str,
}

impl CreateOnlyArtifact {
    pub fn bind(
        path: &Path,
        input_root: &Path,
        label: &'static str,
    ) -> Result<Self, ArtifactError> {
        let absolute = if path.is_absolute() {
            path.to_path_buf()
        } else {
            std::env::current_dir()
                .map_err(|error| ArtifactError(format!("cannot resolve {label}: {error}")))?
                .join(path)
        };
        let parent_path = absolute
            .parent()
            .ok_or_else(|| ArtifactError(format!("{label} has no parent directory")))?;
        let name = absolute
            .file_name()
            .ok_or_else(|| ArtifactError(format!("{label} has no filename")))?
            .to_owned();
        let canonical_parent = fs::canonicalize(parent_path).map_err(|error| {
            ArtifactError(format!(
                "{label} parent must already exist and be real: {error}"
            ))
        })?;
        let canonical_input = fs::canonicalize(input_root)
            .map_err(|error| ArtifactError(format!("cannot resolve input root: {error}")))?;
        if canonical_parent.starts_with(&canonical_input) {
            return Err(ArtifactError(format!(
                "{label} must be outside the measured input root"
            )));
        }
        let parent = cap_fs::open_ambient_dir(&canonical_parent, ambient_authority())
            .map_err(|error| ArtifactError(format!("cannot retain {label} parent: {error}")))?;
        let listed_parent = fs::symlink_metadata(&canonical_parent)
            .map_err(|error| ArtifactError(format!("cannot inspect {label} parent: {error}")))?;
        let parent_identity = parent
            .metadata()
            .map_err(|error| ArtifactError(format!("cannot inspect {label} parent: {error}")))?;
        if !same_directory_identity(&listed_parent, &parent_identity) {
            return Err(ArtifactError(format!(
                "{label} parent changed while it was retained"
            )));
        }
        match cap_fs::stat(&parent, Path::new(&name), cap_fs::FollowSymlinks::No) {
            Ok(_) => {
                return Err(ArtifactError(format!(
                    "{label} already exists: {}",
                    absolute.display()
                )));
            }
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
            Err(error) => {
                return Err(ArtifactError(format!("cannot inspect {label}: {error}")));
            }
        }
        Ok(Self {
            parent,
            parent_path: canonical_parent.clone(),
            parent_identity,
            public_path: canonical_parent.join(&name),
            name,
            label,
        })
    }

    #[must_use]
    pub fn public_path(&self) -> &Path {
        &self.public_path
    }

    pub fn publish(&self, bytes: &[u8], max_bytes: usize) -> Result<(), ArtifactError> {
        if bytes.len() > max_bytes {
            return Err(ArtifactError(format!("{} exceeds byte limit", self.label)));
        }
        self.recheck_parent()?;
        let name = Path::new(&self.name);
        let mut options = cap_fs::OpenOptions::new();
        options.write(true).create_new(true);
        let mut file = cap_fs::open(&self.parent, name, &options)
            .map_err(|error| ArtifactError(format!("cannot create {}: {error}", self.label)))?;
        if let Err(error) = file.write_all(bytes).and_then(|_| file.sync_all()) {
            return Err(ArtifactError(format!(
                "cannot write {}: {error}",
                self.label
            )));
        }
        #[cfg(unix)]
        self.parent.sync_all().map_err(|error| {
            ArtifactError(format!("cannot sync {} directory: {error}", self.label))
        })?;
        self.recheck_parent()?;
        Ok(())
    }

    fn recheck_parent(&self) -> Result<(), ArtifactError> {
        let listed = fs::symlink_metadata(&self.parent_path).map_err(|error| {
            ArtifactError(format!("cannot recheck {} parent: {error}", self.label))
        })?;
        let opened = self.parent.metadata().map_err(|error| {
            ArtifactError(format!("cannot recheck {} parent: {error}", self.label))
        })?;
        if !same_directory_identity(&self.parent_identity, &opened)
            || !same_directory_identity(&self.parent_identity, &listed)
        {
            return Err(ArtifactError(format!(
                "{} parent changed before publication",
                self.label
            )));
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    #[test]
    fn output_is_create_only_and_outside_input() {
        let root = tempdir().unwrap();
        let input = root.path().join("input");
        let outside = root.path().join("outside");
        fs::create_dir(&input).unwrap();
        fs::create_dir(&outside).unwrap();
        assert!(CreateOnlyArtifact::bind(&input.join("out.json"), &input, "test").is_err());
        let output = outside.join("out.json");
        let artifact = CreateOnlyArtifact::bind(&output, &input, "test").unwrap();
        artifact.publish(b"{}\n", 16).unwrap();
        assert_eq!(fs::read(&output).unwrap(), b"{}\n");
        assert!(CreateOnlyArtifact::bind(&output, &input, "test").is_err());
    }

    #[cfg(unix)]
    #[test]
    fn parent_replacement_is_rejected_before_publication() {
        let root = tempdir().unwrap();
        let input = root.path().join("input");
        let outside = root.path().join("outside");
        let displaced = root.path().join("displaced");
        fs::create_dir(&input).unwrap();
        fs::create_dir(&outside).unwrap();
        let output = outside.join("out.json");
        let artifact = CreateOnlyArtifact::bind(&output, &input, "test").unwrap();

        fs::rename(&outside, &displaced).unwrap();
        fs::create_dir(&outside).unwrap();

        assert!(artifact.publish(b"{}\n", 16).is_err());
        assert!(!output.exists());
        assert!(!displaced.join("out.json").exists());
    }
}
