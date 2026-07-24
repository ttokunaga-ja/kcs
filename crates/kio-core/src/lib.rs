//! Core types shared by Kio crates.

pub mod cas;
pub mod dag;
pub mod error;
pub mod exit_code;
pub mod history;
pub mod portable;
pub mod purge;
pub mod schema;
pub mod scope;
pub mod xdg;

pub use error::{KioError, Result};
pub use exit_code::ExitCode;
