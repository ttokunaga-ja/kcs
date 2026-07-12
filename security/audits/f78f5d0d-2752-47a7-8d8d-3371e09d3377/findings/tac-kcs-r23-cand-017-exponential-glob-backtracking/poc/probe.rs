use std::time::Instant;

fn wildcard_match_bytes(pattern: &[u8], value: &[u8], calls: &mut u128) -> bool {
    *calls += 1;
    if pattern.is_empty() {
        return value.is_empty();
    }
    if pattern.starts_with(b"**/") {
        return wildcard_match_bytes(&pattern[3..], value, calls)
            || value
                .iter()
                .position(|byte| *byte == b'/')
                .map(|slash| wildcard_match_bytes(pattern, &value[slash + 1..], calls))
                .unwrap_or(false);
    }
    if pattern == b"**" {
        return true;
    }
    match pattern[0] {
        b'*' => {
            wildcard_match_bytes(&pattern[1..], value, calls)
                || !value.is_empty()
                    && value[0] != b'/'
                    && wildcard_match_bytes(pattern, &value[1..], calls)
        }
        b'?' => {
            !value.is_empty()
                && value[0] != b'/'
                && wildcard_match_bytes(&pattern[1..], &value[1..], calls)
        }
        byte => {
            !value.is_empty()
                && byte == value[0]
                && wildcard_match_bytes(&pattern[1..], &value[1..], calls)
        }
    }
}

fn expected_calls(n: u32) -> u128 {
    (1u128 << (n + 2)) - 3
}

fn main() {
    println!("[+] bounded offline probe for KCS recursive star matching");
    println!("[+] pattern family: (*a)^n b against a^n");
    println!(
        "{:>4} {:>14} {:>14} {:>14} {:>10} {:>12}",
        "n", "pattern_bytes", "value_bytes", "calls", "matched", "elapsed_us"
    );

    for n in [8u32, 10, 12, 14, 16, 18] {
        let pattern = format!("{}b", "*a".repeat(n as usize));
        let value = "a".repeat(n as usize);
        let mut calls = 0;
        let started = Instant::now();
        let matched = wildcard_match_bytes(pattern.as_bytes(), value.as_bytes(), &mut calls);
        let elapsed_us = started.elapsed().as_micros();
        let expected = expected_calls(n);
        if matched || calls != expected {
            eprintln!(
                "unexpected result at n={n}: matched={matched}, calls={calls}, expected={expected}"
            );
            std::process::exit(1);
        }
        println!(
            "{n:>4} {:>14} {:>14} {:>14} {:>10} {:>12}",
            pattern.len(),
            value.len(),
            calls,
            matched,
            elapsed_us
        );
    }

    let mut control_calls = 0;
    let started = Instant::now();
    let control = wildcard_match_bytes(b"a*b", b"aaaaaaaaab", &mut control_calls);
    println!(
        "[+] linear control a*b vs aaaaaaaaab: matched={}, calls={}, elapsed_us={}",
        control,
        control_calls,
        started.elapsed().as_micros()
    );
    println!("[+] recurrence validated through n=18; larger cases intentionally not executed");
}
