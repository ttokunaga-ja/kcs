//! Typed D1 measurement schema.
//!
//! D1 execution remains a manual P4 gate.  This schema makes absence and a
//! blocked run first-class evidence so a consumer cannot reinterpret either as
//! a measured zero or a passing result.

use kio_core::cas::{canonical_json_bytes, is_hash};
use serde::{Deserialize, Serialize};
use thiserror::Error;

pub const D1_SCHEMA_VERSION: u64 = 1;
pub const D1_BENCHMARK_ID: &str = "kio-eval d1/v1";

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "state", rename_all = "kebab-case", deny_unknown_fields)]
pub enum Measurement<T> {
    Measured { value: T, evidence_sha256: String },
    NotMeasured { reason: String },
    Blocked { reason: String },
}

impl<T> Measurement<T> {
    fn validate(&self, field: &str) -> Result<(), D1Error> {
        match self {
            Self::Measured {
                evidence_sha256, ..
            } if !is_hash(evidence_sha256) => Err(D1Error::Invalid(format!(
                "{field} measured evidence digest is invalid"
            ))),
            Self::NotMeasured { reason } | Self::Blocked { reason } if reason.trim().is_empty() => {
                Err(D1Error::Invalid(format!("{field} reason is empty")))
            }
            _ => Ok(()),
        }
    }

    const fn class(&self) -> D1Assessment {
        match self {
            Self::Measured { .. } => D1Assessment::Measured,
            Self::NotMeasured { .. } => D1Assessment::NotMeasured,
            Self::Blocked { .. } => D1Assessment::Blocked,
        }
    }
}

/// Durations are integer milliseconds and costs are integer micro-US dollars.
/// Integer units keep the canonical report byte-stable and avoid accepting a
/// non-finite JSON number as measurement evidence.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct D1Report {
    pub schema_version: u64,
    pub benchmark: String,
    pub binary_sha256: String,
    pub fixture_sha256: String,
    pub attestation_sha256: String,
    pub baseline_ttfv_ms: Measurement<u64>,
    pub enriched_ttfv_ms: Measurement<u64>,
    pub preview_cost_micro_usd: Measurement<u64>,
    pub actual_cost_micro_usd: Measurement<u64>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum D1Assessment {
    Measured,
    NotMeasured,
    Blocked,
}

#[derive(Debug, Error, PartialEq, Eq)]
pub enum D1Error {
    #[error("invalid D1 report: {0}")]
    Invalid(String),
    #[error("D1 report JSON failed: {0}")]
    Json(String),
    #[error("D1 report is not canonical JCS plus LF")]
    NonCanonical,
}

impl D1Report {
    pub fn validate(&self) -> Result<(), D1Error> {
        if self.schema_version != D1_SCHEMA_VERSION || self.benchmark != D1_BENCHMARK_ID {
            return Err(D1Error::Invalid(
                "schema version or benchmark identity differs".into(),
            ));
        }
        for (field, digest) in [
            ("binary_sha256", self.binary_sha256.as_str()),
            ("fixture_sha256", self.fixture_sha256.as_str()),
            ("attestation_sha256", self.attestation_sha256.as_str()),
        ] {
            if !is_hash(digest) {
                return Err(D1Error::Invalid(format!("{field} is invalid")));
            }
        }
        self.baseline_ttfv_ms.validate("baseline_ttfv_ms")?;
        self.enriched_ttfv_ms.validate("enriched_ttfv_ms")?;
        self.preview_cost_micro_usd
            .validate("preview_cost_micro_usd")?;
        self.actual_cost_micro_usd
            .validate("actual_cost_micro_usd")?;
        Ok(())
    }

    /// A report is measured only when all four values are measured. Any
    /// blocked field dominates; every other partial report remains explicitly
    /// not measured and cannot be upgraded to pass by a caller.
    pub fn assessment(&self) -> Result<D1Assessment, D1Error> {
        self.validate()?;
        let classes = [
            self.baseline_ttfv_ms.class(),
            self.enriched_ttfv_ms.class(),
            self.preview_cost_micro_usd.class(),
            self.actual_cost_micro_usd.class(),
        ];
        Ok(if classes.contains(&D1Assessment::Blocked) {
            D1Assessment::Blocked
        } else if classes.iter().all(|state| *state == D1Assessment::Measured) {
            D1Assessment::Measured
        } else {
            D1Assessment::NotMeasured
        })
    }

    pub fn to_canonical_bytes(&self) -> Result<Vec<u8>, D1Error> {
        self.validate()?;
        let value = serde_json::to_value(self).map_err(|error| D1Error::Json(error.to_string()))?;
        let mut bytes =
            canonical_json_bytes(&value).map_err(|error| D1Error::Json(error.to_string()))?;
        bytes.push(b'\n');
        Ok(bytes)
    }

    pub fn from_canonical_bytes(bytes: &[u8]) -> Result<Self, D1Error> {
        let report: Self =
            serde_json::from_slice(bytes).map_err(|error| D1Error::Json(error.to_string()))?;
        report.validate()?;
        if report.to_canonical_bytes()? != bytes {
            return Err(D1Error::NonCanonical);
        }
        Ok(report)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn hash(byte: char) -> String {
        format!("sha256:{}", byte.to_string().repeat(64))
    }

    fn report() -> D1Report {
        D1Report {
            schema_version: D1_SCHEMA_VERSION,
            benchmark: D1_BENCHMARK_ID.into(),
            binary_sha256: hash('1'),
            fixture_sha256: hash('2'),
            attestation_sha256: hash('3'),
            baseline_ttfv_ms: Measurement::Measured {
                value: 1_000,
                evidence_sha256: hash('4'),
            },
            enriched_ttfv_ms: Measurement::Measured {
                value: 2_000,
                evidence_sha256: hash('5'),
            },
            preview_cost_micro_usd: Measurement::Measured {
                value: 125,
                evidence_sha256: hash('6'),
            },
            actual_cost_micro_usd: Measurement::Measured {
                value: 150,
                evidence_sha256: hash('7'),
            },
        }
    }

    #[test]
    fn canonical_round_trip_preserves_complete_measurement() {
        let report = report();
        let bytes = report.to_canonical_bytes().unwrap();
        assert_eq!(D1Report::from_canonical_bytes(&bytes).unwrap(), report);
        assert_eq!(report.assessment().unwrap(), D1Assessment::Measured);
    }

    #[test]
    fn incomplete_and_blocked_measurements_fail_closed() {
        let mut incomplete = report();
        incomplete.enriched_ttfv_ms = Measurement::NotMeasured {
            reason: "P4 manual D1 corpus was not executed".into(),
        };
        assert_eq!(incomplete.assessment().unwrap(), D1Assessment::NotMeasured);

        incomplete.actual_cost_micro_usd = Measurement::Blocked {
            reason: "pricing evidence unavailable".into(),
        };
        assert_eq!(incomplete.assessment().unwrap(), D1Assessment::Blocked);
    }

    #[test]
    fn malformed_or_ambiguous_measurement_is_rejected() {
        let mut invalid = report();
        invalid.baseline_ttfv_ms = Measurement::NotMeasured { reason: "".into() };
        assert!(invalid.validate().is_err());

        let bytes = report().to_canonical_bytes().unwrap();
        let pretty = serde_json::to_vec_pretty(
            &serde_json::from_slice::<serde_json::Value>(&bytes).unwrap(),
        )
        .unwrap();
        assert_eq!(
            D1Report::from_canonical_bytes(&pretty),
            Err(D1Error::NonCanonical)
        );
    }
}
