//! Read-only Phase 4 GC planning entry point.
//!
//! This module deliberately has no receipt writer, CAS remover, index handle,
//! or store lock.  The public CLI milestone can only bind the immutable planner
//! and serialize its result.

use kio_core::gc::GcPlanner;
use kio_core::scope::{now_utc_seconds, parse_utc_seconds};
use kio_core::{KioError, Result};
use serde_json::Value;

pub(super) fn run_gc_dry_run() -> Result<Value> {
    let now = now_utc_seconds();
    let now_unix_seconds = parse_utc_seconds(&now)
        .ok_or_else(|| KioError::schema("current time is not canonical UTC seconds"))?;
    let plan = GcPlanner::bind_current()?.plan_at(now_unix_seconds)?;
    serde_json::to_value(plan).map_err(|error| KioError::schema(error.to_string()))
}
