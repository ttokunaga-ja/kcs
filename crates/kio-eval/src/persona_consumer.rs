//! Strict consumption of a closed, plan-owned persona artifact bundle.
//!
//! The individual artifact parsers remain the sole schema authorities.  This
//! module binds their exact source bytes to the descriptor-relative artifact
//! boundary, then retains that identity for a final pre-mutation recheck.

use crate::{
    persona_artifact::{self, PersonaArtifactError, StrictArtifact},
    persona_plan::{self, PersonaPlan, PersonaPlanError, PersonaProfile},
    persona_render_artifact::{self, RenderArtifact, RenderArtifactError},
    persona_schedule::{self, PersonaScheduleError, SuiteSchedule},
};
use kio_core::cas::hash_bytes;
use std::path::Path;
use thiserror::Error;

#[derive(Debug, Error)]
pub enum CanonicalPersonaBundleError {
    #[error("persona artifact boundary: {0}")]
    Boundary(#[from] PersonaArtifactError),
    #[error("persona plan: {0}")]
    Plan(#[from] PersonaPlanError),
    #[error("persona schedule: {0}")]
    Schedule(#[from] PersonaScheduleError),
    #[error("persona render artifact: {0}")]
    Render(#[from] RenderArtifactError),
    #[error("persona bundle identity changed: {0}")]
    Changed(&'static str),
}

/// Immutable identity closed over the plan and all three exact artifact files.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CanonicalPersonaBundleIdentity {
    pub fixture_id: String,
    pub profile: PersonaProfile,
    pub plan_digest: String,
    pub plan_hash: String,
    pub plan_len: u64,
    pub schedule_hash: String,
    pub schedule_len: u64,
    pub render_hash: String,
    pub render_len: u64,
}

/// A canonical plan, suite schedule, and renderer receipt read as one bundle.
///
/// Source paths and bytes are retained so callers can prove that the bundle did
/// not change between validation and a subsequent filesystem mutation.
#[derive(Debug)]
pub struct CanonicalPersonaBundle {
    pub plan_source: StrictArtifact,
    pub schedule_source: StrictArtifact,
    pub render_source: StrictArtifact,
    pub plan: PersonaPlan,
    pub schedule: SuiteSchedule,
    pub render: RenderArtifact,
    pub identity: CanonicalPersonaBundleIdentity,
}

impl CanonicalPersonaBundle {
    /// Read, parse, and bind the three exact canonical artifacts.
    pub fn load(
        plan_path: &Path,
        schedule_path: &Path,
        render_path: &Path,
    ) -> Result<Self, CanonicalPersonaBundleError> {
        let plan_source =
            persona_artifact::bind_strict(plan_path, persona_plan::MAX_CANONICAL_BYTES)?;
        let plan = PersonaPlan::parse_canonical(plan_source.bytes())?;
        let schedule_source =
            persona_artifact::bind_strict(schedule_path, persona_schedule::MAX_CANONICAL_BYTES)?;
        let schedule = SuiteSchedule::parse_canonical(&plan, schedule_source.bytes())?;
        let render_source = persona_artifact::bind_strict(
            render_path,
            persona_render_artifact::MAX_CANONICAL_BYTES,
        )?;
        let render = RenderArtifact::parse_canonical(&plan, render_source.bytes())?;

        let plan_digest = plan.digest()?;
        let identity = CanonicalPersonaBundleIdentity {
            fixture_id: plan.fixture_id.clone(),
            profile: plan.profile,
            plan_digest,
            plan_hash: hash_bytes(plan_source.bytes()),
            plan_len: plan_source.bytes().len() as u64,
            schedule_hash: hash_bytes(schedule_source.bytes()),
            schedule_len: schedule_source.bytes().len() as u64,
            render_hash: hash_bytes(render_source.bytes()),
            render_len: render_source.bytes().len() as u64,
        };
        Ok(Self {
            plan_source,
            schedule_source,
            render_source,
            plan,
            schedule,
            render,
            identity,
        })
    }

    /// Re-read every source through the strict boundary immediately before a
    /// caller performs a later mutation.
    pub fn recheck_sources(&self) -> Result<(), CanonicalPersonaBundleError> {
        self.plan_source
            .recheck()
            .map_err(|_| CanonicalPersonaBundleError::Changed("plan source"))?;
        self.schedule_source
            .recheck()
            .map_err(|_| CanonicalPersonaBundleError::Changed("schedule source"))?;
        self.render_source
            .recheck()
            .map_err(|_| CanonicalPersonaBundleError::Changed("render source"))?;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{
        persona_plan::frozen_plan, persona_render_artifact::RenderArtifact,
        persona_schedule::build_suite_schedule,
    };
    use kio_core::cas::canonical_json_bytes;
    use serde_json::Value;
    use std::{fs, path::PathBuf, sync::OnceLock};
    use tempfile::tempdir;

    struct GeneratedBundle {
        plan: Vec<u8>,
        schedule: Vec<u8>,
        render: Vec<u8>,
    }

    static TINY: OnceLock<GeneratedBundle> = OnceLock::new();
    static PILOT: OnceLock<GeneratedBundle> = OnceLock::new();
    static FULL: OnceLock<GeneratedBundle> = OnceLock::new();

    fn generated(profile: PersonaProfile) -> &'static GeneratedBundle {
        let slot = match profile {
            PersonaProfile::Tiny => &TINY,
            PersonaProfile::Pilot => &PILOT,
            PersonaProfile::Full => &FULL,
        };
        slot.get_or_init(|| {
            let plan = frozen_plan(profile);
            let schedule = build_suite_schedule(&plan).unwrap();
            let render = RenderArtifact::build(&plan).unwrap();
            GeneratedBundle {
                plan: plan.canonical_bytes().unwrap(),
                schedule: schedule.canonical_bytes().unwrap(),
                render: render.canonical_bytes().unwrap(),
            }
        })
    }

    fn write_bundle(profile: PersonaProfile) -> (tempfile::TempDir, PathBuf, PathBuf, PathBuf) {
        let root = tempdir().unwrap();
        let root_path = fs::canonicalize(root.path()).unwrap();
        let generated = generated(profile);
        let plan_path = root_path.join("plan.json");
        let schedule_path = root_path.join("schedule.json");
        let render_path = root_path.join("render.json");
        fs::write(&plan_path, &generated.plan).unwrap();
        fs::write(&schedule_path, &generated.schedule).unwrap();
        fs::write(&render_path, &generated.render).unwrap();
        (root, plan_path, schedule_path, render_path)
    }

    #[test]
    fn loads_actual_generated_canonical_artifacts_for_every_profile() {
        for profile in [
            PersonaProfile::Tiny,
            PersonaProfile::Pilot,
            PersonaProfile::Full,
        ] {
            let (_root, plan, schedule, render) = write_bundle(profile);
            let bundle = CanonicalPersonaBundle::load(&plan, &schedule, &render).unwrap();
            assert_eq!(bundle.identity.profile, profile);
            assert_eq!(bundle.identity.plan_digest, bundle.plan.digest().unwrap());
            assert_eq!(
                bundle.identity.plan_hash,
                hash_bytes(bundle.plan_source.bytes())
            );
            assert_eq!(
                bundle.identity.schedule_hash,
                hash_bytes(bundle.schedule_source.bytes())
            );
            assert_eq!(
                bundle.identity.render_hash,
                hash_bytes(bundle.render_source.bytes())
            );
            bundle.recheck_sources().unwrap();
        }
    }

    #[test]
    fn rejects_handcrafted_partial_plan_and_cross_plan_artifacts() {
        let (_root, plan, schedule, render) = write_bundle(PersonaProfile::Tiny);
        fs::write(&plan, b"{\"schema\":\"kio.persona.plan/v2\"}\n").unwrap();
        assert!(CanonicalPersonaBundle::load(&plan, &schedule, &render).is_err());

        let (_root, plan, schedule, render) = write_bundle(PersonaProfile::Tiny);
        let tiny = frozen_plan(PersonaProfile::Tiny);
        let digest = tiny.digest().unwrap();
        let fixture_id = tiny.fixture_id.clone();
        let profile = tiny.profile;
        write_canonical(
            &schedule,
            &serde_json::json!({
                "schema": crate::persona_schedule::SCHEMA,
                "plan_digest": digest.clone(),
            }),
        );
        assert!(CanonicalPersonaBundle::load(&plan, &schedule, &render).is_err());

        let (_root, plan, schedule, render) = write_bundle(PersonaProfile::Tiny);
        write_canonical(
            &render,
            &serde_json::json!({
                "schema": crate::persona_render_artifact::SCHEMA,
                "fixture_id": fixture_id,
                "profile": profile,
                "plan_digest": digest,
            }),
        );
        assert!(CanonicalPersonaBundle::load(&plan, &schedule, &render).is_err());

        let (_other_root, other_plan, _other_schedule, _other_render) =
            write_bundle(PersonaProfile::Pilot);
        let (_root, plan, schedule, render) = write_bundle(PersonaProfile::Tiny);
        fs::copy(&other_plan, &plan).unwrap();
        assert!(CanonicalPersonaBundle::load(&plan, &schedule, &render).is_err());
    }

    #[test]
    fn rejects_noncanonical_and_noncanonical_plan_shapes() {
        let (_root, plan, schedule, render) = write_bundle(PersonaProfile::Tiny);
        let original = fs::read(&plan).unwrap();

        let mut unknown: Value = serde_json::from_slice(&original).unwrap();
        unknown
            .as_object_mut()
            .unwrap()
            .insert("unknown".into(), Value::Null);
        reject_plan_shape(&plan, &schedule, &render, &unknown);

        let mut missing: Value = serde_json::from_slice(&original).unwrap();
        missing.as_object_mut().unwrap().remove("fixture_id");
        reject_plan_shape(&plan, &schedule, &render, &missing);

        let mut missing_person: Value = serde_json::from_slice(&original).unwrap();
        missing_person["personas"].as_array_mut().unwrap().pop();
        reject_plan_shape(&plan, &schedule, &render, &missing_person);

        let mut missing_scope: Value = serde_json::from_slice(&original).unwrap();
        missing_scope["personas"][0]["scopes"]
            .as_array_mut()
            .unwrap()
            .pop();
        reject_plan_shape(&plan, &schedule, &render, &missing_scope);

        let mut extra_person: Value = serde_json::from_slice(&original).unwrap();
        let people = extra_person["personas"].as_array_mut().unwrap();
        people.push(people[0].clone());
        reject_plan_shape(&plan, &schedule, &render, &extra_person);

        let mut extra_scope: Value = serde_json::from_slice(&original).unwrap();
        let scopes = extra_scope["personas"][0]["scopes"].as_array_mut().unwrap();
        scopes.push(scopes[0].clone());
        reject_plan_shape(&plan, &schedule, &render, &extra_scope);

        let mut reordered: Value = serde_json::from_slice(&original).unwrap();
        reordered["personas"].as_array_mut().unwrap().reverse();
        reject_plan_shape(&plan, &schedule, &render, &reordered);

        fs::write(&plan, b"{\"fixture_id\":\"x\",\"fixture_id\":\"x\"}\n").unwrap();
        assert!(CanonicalPersonaBundle::load(&plan, &schedule, &render).is_err());

        let mut whitespace = vec![b' '];
        whitespace.extend_from_slice(&original);
        fs::write(&plan, whitespace).unwrap();
        assert!(CanonicalPersonaBundle::load(&plan, &schedule, &render).is_err());
    }

    fn reject_plan_shape(plan: &Path, schedule: &Path, render: &Path, value: &Value) {
        let mut bytes = canonical_json_bytes(value).unwrap();
        bytes.push(b'\n');
        fs::write(plan, bytes).unwrap();
        assert!(CanonicalPersonaBundle::load(plan, schedule, render).is_err());
    }

    fn write_canonical(path: &Path, value: &Value) {
        let mut bytes = canonical_json_bytes(value).unwrap();
        bytes.push(b'\n');
        fs::write(path, bytes).unwrap();
    }

    #[test]
    fn rejects_schedule_and_render_from_another_plan() {
        let (_tiny_root, plan, schedule, render) = write_bundle(PersonaProfile::Tiny);
        let mut forged_schedule: Value =
            serde_json::from_slice(&fs::read(&schedule).unwrap()).unwrap();
        forged_schedule["plan_digest"] = Value::String(format!("sha256:{}", "0".repeat(64)));
        write_canonical(&schedule, &forged_schedule);
        assert!(CanonicalPersonaBundle::load(&plan, &schedule, &render).is_err());

        let (_tiny_root, plan, schedule, render) = write_bundle(PersonaProfile::Tiny);
        let mut forged_render: Value = serde_json::from_slice(&fs::read(&render).unwrap()).unwrap();
        forged_render["plan_digest"] = Value::String(format!("sha256:{}", "0".repeat(64)));
        write_canonical(&render, &forged_render);
        assert!(CanonicalPersonaBundle::load(&plan, &schedule, &render).is_err());

        let (_tiny_root, plan, schedule, render) = write_bundle(PersonaProfile::Tiny);
        let (_pilot_root, _other_plan, other_schedule, other_render) =
            write_bundle(PersonaProfile::Pilot);
        fs::copy(&other_schedule, &schedule).unwrap();
        assert!(CanonicalPersonaBundle::load(&plan, &schedule, &render).is_err());

        let (_tiny_root, plan, schedule, render) = write_bundle(PersonaProfile::Tiny);
        fs::copy(&other_render, &render).unwrap();
        assert!(CanonicalPersonaBundle::load(&plan, &schedule, &render).is_err());
    }

    #[test]
    fn recheck_rejects_replaced_source_bytes() {
        let (_root, plan, schedule, render) = write_bundle(PersonaProfile::Tiny);
        let bundle = CanonicalPersonaBundle::load(&plan, &schedule, &render).unwrap();
        fs::write(&schedule, bundle.plan_source.bytes()).unwrap();
        assert!(matches!(
            bundle.recheck_sources(),
            Err(CanonicalPersonaBundleError::Changed("schedule source"))
        ));
    }

    #[test]
    fn recheck_rejects_same_content_inode_replacement() {
        let (_root, plan, schedule, render) = write_bundle(PersonaProfile::Tiny);
        let bundle = CanonicalPersonaBundle::load(&plan, &schedule, &render).unwrap();
        let replacement = schedule.with_file_name("replacement.json");
        fs::write(&replacement, bundle.schedule_source.bytes()).unwrap();
        #[cfg(unix)]
        fs::rename(&replacement, &schedule).unwrap();
        #[cfg(windows)]
        {
            fs::remove_file(&schedule).unwrap();
            fs::rename(&replacement, &schedule).unwrap();
        }
        assert!(matches!(
            bundle.recheck_sources(),
            Err(CanonicalPersonaBundleError::Changed("schedule source"))
        ));
    }
}
