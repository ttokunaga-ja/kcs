```rs
#[derive(Debug, Clone)]
pub struct DilutionPoint { pub dilution: f64, pub observed_signal: f64 }

pub fn recovery_percent(reference: f64, observed: f64) -> f64 {
    if reference <= 0.0 { return f64::NAN; }
    (observed / reference) * 100.0
}

pub fn accepted(point: &DilutionPoint, reference: f64) -> bool {
    let recovery = recovery_percent(reference, point.observed_signal);
    (80.0..=120.0).contains(&recovery) && point.dilution > 0.0
}
```
