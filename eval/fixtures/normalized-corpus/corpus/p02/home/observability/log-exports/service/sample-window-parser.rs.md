```rs
//! Parse compact gateway log exports into per-route counts for incident review.

use std::collections::BTreeMap;
use std::io::{self, BufRead};

#[derive(Default)]
struct RouteTotals {
    requests: u64,
    failures: u64,
}

fn main() {
    let mut totals: BTreeMap<String, RouteTotals> = BTreeMap::new();

    for line in io::stdin().lock().lines().map_while(Result::ok) {
        let route = field(&line, "route").unwrap_or("unknown");
        let status = field(&line, "status").unwrap_or("0");
        let entry = totals.entry(route.to_owned()).or_default();
        entry.requests += 1;
        if status.starts_with('5') {
            entry.failures += 1;
        }
    }

    println!("route,requests,failures");
    for (route, counts) in totals {
        println!("{route},{},{}", counts.requests, counts.failures);
    }
}

fn field<'a>(line: &'a str, name: &str) -> Option<&'a str> {
    line.split_whitespace()
        .find_map(|part| part.strip_prefix(&format!("{name}=")))
}
```
