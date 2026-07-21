//! `cost-ledger.sqlite`: the device-global cost/Batch-intent store (04-pipeline.md
//! §5.4 DDL, §5.8 2-phase protocol). Replaces the JSONL 3-file `budget::CostLedger`
//! / `budget::ReservationLedger` design (10-operations.md §12.7 rename table);
//! module split:
//!
//! - [`schema`] — DDL-of-record, connection bootstrap, canonical shape self-heal
//! - [`time`] — UTC epoch-ms calendar helpers (10 §12.4's one ISO8601 exception)
//! - [`model`] — row/enum types
//! - [`migrate`] — one-time JSONL → SQLite cutover (10 §7.5.3)
//! - [`ops`] — the §5.8/§5.4 state machine: phase 1-3, idempotent recording,
//!   outcome validation, crash recovery, sync degenerate 2-phase, the
//!   query-embedding device row, budget cap check-then-reserve, and abandon.

pub mod migrate;
pub mod model;
pub mod ops;
pub mod schema;
pub mod time;

pub use migrate::{migrate_jsonl_if_needed, JsonlMigrationOutcome};
pub use model::{BatchRequestRow, BatchState, CostLedgerRow, Outcome, RequestKind, TaskKey};
pub use schema::{default_ledger_path, LedgerDb};
