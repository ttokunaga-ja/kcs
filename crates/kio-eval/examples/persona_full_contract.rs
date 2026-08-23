//! Explicit Full persona-contract validation. This is intentionally not part
//! of the ordinary test lane: it creates the 195k-source / 2.4m-chunk fixture.

use kio_eval::{
    persona_plan::{FULL_PLAN_HASH, PersonaProfile, frozen_plan, source_projections},
    persona_render_artifact::{FULL_ARTIFACT_HASH, MAX_CANONICAL_BYTES, RenderArtifact},
    persona_schedule::{MAX_CANONICAL_BYTES as MAX_SCHEDULE_BYTES, build_suite_schedule},
};
use serde_json::json;

fn main() {
    let plan = frozen_plan(PersonaProfile::Full);
    plan.validate().expect("frozen Full plan validates");
    assert_eq!(plan.digest().expect("plan digest"), FULL_PLAN_HASH);

    let mut source_count = 0_u32;
    let mut chunk_count = 0_u32;
    for person in &plan.personas {
        let sources = source_projections(person).expect("Full source projection");
        source_count += u32::try_from(sources.len()).expect("source count fits u32");
        chunk_count += sources
            .iter()
            .map(|source| source.planned_chunks)
            .sum::<u32>();
    }
    assert_eq!(source_count, 195_000);
    assert_eq!(chunk_count, 2_400_000);

    let schedule = build_suite_schedule(&plan).expect("Full suite schedule");
    let schedule_bytes = schedule
        .canonical_bytes()
        .expect("schedule canonical bytes");
    let render = RenderArtifact::build(&plan).expect("Full render artifact");
    let render_bytes = render.canonical_bytes().expect("render canonical bytes");
    assert_eq!(render.source_count, source_count);
    assert_eq!(render.artifact_digest, FULL_ARTIFACT_HASH);
    assert_eq!(
        schedule.suite_digest,
        "sha256:028a26df50a8aa94b33ed9a8edd306dac8baf588950e70b4857c0b2e617a4529"
    );
    assert_eq!(
        schedule.people[0].schedule_digest,
        "sha256:0bb6ad9c9b95c318a2d938192e8663cd5ad5ccde9e156cb163bc8875e27ce56f"
    );
    assert!(schedule_bytes.len() <= MAX_SCHEDULE_BYTES);
    assert!(render_bytes.len() <= MAX_CANONICAL_BYTES);

    println!(
        "{}",
        serde_json::to_string(&json!({
            "chunks": chunk_count,
            "plan_digest": FULL_PLAN_HASH,
            "render_bytes": render_bytes.len(),
            "render_digest": FULL_ARTIFACT_HASH,
            "schedule_bytes": schedule_bytes.len(),
            "schedule_digest": schedule.suite_digest,
            "sources": source_count,
        }))
        .expect("summary JSON")
    );
}
