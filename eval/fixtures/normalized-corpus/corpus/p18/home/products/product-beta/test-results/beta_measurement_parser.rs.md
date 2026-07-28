```rs
use std::collections::BTreeMap;

pub fn parse_measurement_row(line: &str) -> Option<BTreeMap<String, String>> {
    let fields: Vec<&str> = line.trim().split('\t').collect();
    if fields.len() != 4 {
        return None;
    }

    Some(BTreeMap::from([
        ("lot".into(), fields[0].into()),
        ("station".into(), fields[1].into()),
        ("feature".into(), fields[2].into()),
        ("result".into(), fields[3].into()),
    ]))
}
```
