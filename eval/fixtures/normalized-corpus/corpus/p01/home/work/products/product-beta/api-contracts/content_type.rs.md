```rs
//! Parses the media type portion of a Content-Type header.

pub fn media_type(value: &str) -> Option<&str> {
    let candidate = value.split(';').next()?.trim();
    if candidate.contains('/') {
        Some(candidate)
    } else {
        None
    }
}

pub fn accepts_json(value: &str) -> bool {
    media_type(value)
        .map(|candidate| candidate.eq_ignore_ascii_case("application/json"))
        .unwrap_or(false)
}
```
