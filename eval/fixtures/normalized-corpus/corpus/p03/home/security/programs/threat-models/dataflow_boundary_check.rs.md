```rs
//! Small consistency check for threat-model data-flow inventories.
//! A flow can cross a boundary only when both ends name their trust zone explicitly.

use std::collections::BTreeSet;

#[derive(Debug, Clone)]
pub struct DataFlow {
    pub name: String,
    pub source_zone: String,
    pub destination_zone: String,
    pub classification: String,
    pub reviewed: bool,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BoundaryFinding {
    pub flow: String,
    pub reason: String,
}

pub fn check(flows: &[DataFlow], approved_zones: &BTreeSet<String>) -> Vec<BoundaryFinding> {
    let mut findings = Vec::new();
    for flow in flows {
        if flow.source_zone.trim().is_empty() || flow.destination_zone.trim().is_empty() {
            findings.push(BoundaryFinding {
                flow: flow.name.clone(),
                reason: "source or destination trust zone is missing".into(),
            });
            continue;
        }
        if !approved_zones.contains(&flow.source_zone) || !approved_zones.contains(&flow.destination_zone) {
            findings.push(BoundaryFinding {
                flow: flow.name.clone(),
                reason: "flow references a zone absent from the reviewed inventory".into(),
            });
        }
        if flow.classification.eq_ignore_ascii_case("restricted") && !flow.reviewed {
            findings.push(BoundaryFinding {
                flow: flow.name.clone(),
                reason: "restricted data flow lacks a recorded review".into(),
            });
        }
    }
    findings
}

pub fn nami_grid_zones() -> BTreeSet<String> {
    ["operator-network", "control-plane", "evidence-vault", "vendor-edge"]
        .into_iter()
        .map(str::to_owned)
        .collect()
}
```
