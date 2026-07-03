//! Core types shared by KCS crates.

pub mod cas;
pub mod dag;
pub mod error;
pub mod exit_code;
pub mod schema;
pub mod scope;

pub use error::{KcsError, Result};
pub use exit_code::ExitCode;
