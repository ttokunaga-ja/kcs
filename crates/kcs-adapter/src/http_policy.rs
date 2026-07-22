//! Shared resource policy for authenticated adapter HTTP exchanges.

use std::io::Read as _;
use std::time::Duration;

use serde_json::Value;

use crate::types::ProviderIdempotency;
use crate::{AdapterError, Result};

pub(crate) const MODEL_CATALOG_MAX_BYTES: usize = 1024 * 1024;
pub(crate) const EMBEDDING_RESPONSE_MAX_BYTES: usize = 8 * 1024 * 1024;
pub(crate) const OCR_RESPONSE_MAX_BYTES: usize = 64 * 1024 * 1024;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) struct HttpPolicy {
    pub(crate) connect_timeout: Duration,
    pub(crate) read_timeout: Duration,
    pub(crate) write_timeout: Duration,
    pub(crate) overall_timeout: Duration,
}

impl Default for HttpPolicy {
    fn default() -> Self {
        Self {
            connect_timeout: Duration::from_secs(30),
            read_timeout: Duration::from_secs(30),
            write_timeout: Duration::from_secs(30),
            overall_timeout: Duration::from_secs(300),
        }
    }
}

/// Authenticated provider requests fail closed on redirects. This prevents a
/// provider-specific credential header from being replayed to a new origin.
pub(crate) fn authenticated_agent(policy: HttpPolicy) -> ureq::Agent {
    // ureq 2 gives `timeout()` precedence over `timeout_read()` and
    // `timeout_write()`. Configure one overall deadline from the strictest
    // policy cap so the nominal read/write limits cannot be silently widened
    // by a longer overall timeout.
    let effective_overall_timeout = effective_overall_timeout(policy);
    ureq::AgentBuilder::new()
        .redirects(0)
        .timeout_connect(policy.connect_timeout)
        .timeout(effective_overall_timeout)
        .build()
}

fn effective_overall_timeout(policy: HttpPolicy) -> Duration {
    policy
        .overall_timeout
        .min(policy.read_timeout)
        .min(policy.write_timeout)
}

pub(crate) fn read_json_bounded(
    response: ureq::Response,
    max_bytes: usize,
    context: &str,
) -> Result<Value> {
    if response
        .header("Content-Encoding")
        .is_some_and(|encoding| !encoding.eq_ignore_ascii_case("identity"))
    {
        return Err(AdapterError::ContractViolation(format!(
            "{context} uses unsupported content encoding"
        )));
    }
    if let Some(content_length) = response.header("Content-Length") {
        if content_length
            .parse::<u64>()
            .ok()
            .is_some_and(|length| length > max_bytes as u64)
        {
            return Err(AdapterError::ContractViolation(format!(
                "{context} exceeds {max_bytes} bytes"
            )));
        }
    }

    let read_limit = max_bytes
        .checked_add(1)
        .ok_or_else(|| AdapterError::ContractViolation("response limit overflow".to_owned()))?;
    let mut body = Vec::with_capacity(max_bytes.min(64 * 1024));
    response
        .into_reader()
        .take(read_limit as u64)
        .read_to_end(&mut body)
        .map_err(|err| AdapterError::Network(format!("{context} read failed: {err}")))?;
    parse_json_bytes_bounded(&body, max_bytes, context)
}

/// QA16 (step4b-contract-tests-p3a.md §F, 07 §4 L290): parse an HTTP
/// `Retry-After` header value into milliseconds. Only the numeric
/// delay-seconds form (RFC 9110 §10.2.3) is supported — the rarer HTTP-date
/// form is not parsed and degrades to `None`, same as a missing header
/// (`AdapterRun.retry_after_ms` is documented `optional`; callers already
/// fall back to the existing exponential backoff when it is absent).
/// Negative, non-finite, or overflowing input also returns `None` rather than
/// a fabricated delay.
pub(crate) fn parse_retry_after_ms(header_value: &str) -> Option<u64> {
    let seconds: f64 = header_value.trim().parse().ok()?;
    if !seconds.is_finite() || seconds < 0.0 {
        return None;
    }
    let millis = (seconds * 1000.0).round();
    if millis > u64::MAX as f64 {
        return None;
    }
    Some(millis as u64)
}

/// QA13 (step4b-contract-tests-p3a.md §E, 04 §5.5 L880): resolve the
/// idempotency header a sync provider call must carry, or fail closed.
/// `NotProvided` never inspects `idempotency_token` — the ledger's own
/// §5.4/§5.8 2-phase record (a `batch_requests` row) is the sole dedup guard,
/// and Adapter-layer idempotency is never required unconditionally (04 §5.5:
/// "Adapter 層への idempotency_key 一律要求はしない"). `HttpHeader(name)`
/// REQUIRES a token; a missing one is fail-closed (04 §5.5 「要求」), never a
/// silent unauthenticated send. Factored out as a pure function (no `ureq`
/// dependency) so both real clients' header assembly is unit-testable
/// without a live HTTP request.
pub(crate) fn resolve_idempotency_header(
    provider_idempotency: &ProviderIdempotency,
    idempotency_token: Option<&str>,
) -> Result<Option<(String, String)>> {
    match provider_idempotency {
        ProviderIdempotency::NotProvided => Ok(None),
        ProviderIdempotency::HttpHeader(name) => {
            let token = idempotency_token.ok_or_else(|| {
                AdapterError::ContractViolation(
                    "provider declares an idempotency key but the caller supplied no token — \
                     04 §5.5 要求 fail-closed"
                        .to_owned(),
                )
            })?;
            Ok(Some((name.clone(), token.to_owned())))
        }
    }
}

pub(crate) fn parse_json_bytes_bounded(
    body: &[u8],
    max_bytes: usize,
    context: &str,
) -> Result<Value> {
    if body.len() > max_bytes {
        return Err(AdapterError::ContractViolation(format!(
            "{context} exceeds {max_bytes} bytes"
        )));
    }
    serde_json::from_slice(body)
        .map_err(|err| AdapterError::ContractViolation(format!("invalid {context} JSON: {err}")))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn retry_after_ms_parses_numeric_seconds_form() {
        assert_eq!(parse_retry_after_ms("30"), Some(30_000));
        assert_eq!(parse_retry_after_ms("0"), Some(0));
        assert_eq!(parse_retry_after_ms("  120  "), Some(120_000));
        assert_eq!(parse_retry_after_ms("2.5"), Some(2_500));
    }

    #[test]
    fn retry_after_ms_rejects_invalid_or_unsupported_forms() {
        // Negative, non-finite, and the (rare, unsupported) HTTP-date form all
        // degrade to `None` rather than a fabricated delay.
        assert_eq!(parse_retry_after_ms("-1"), None);
        assert_eq!(parse_retry_after_ms("NaN"), None);
        assert_eq!(parse_retry_after_ms("Wed, 21 Oct 2026 07:28:00 GMT"), None);
        assert_eq!(parse_retry_after_ms(""), None);
        assert_eq!(parse_retry_after_ms("inf"), None);
    }

    #[test]
    fn bounded_json_accepts_exact_limit_and_rejects_one_over() {
        let exact = br#"{"ok":true}"#;
        assert_eq!(
            parse_json_bytes_bounded(exact, exact.len(), "test response").unwrap()["ok"],
            true
        );

        let err = parse_json_bytes_bounded(exact, exact.len() - 1, "test response").unwrap_err();
        assert!(err.to_string().contains("exceeds"));

        let response = ureq::Response::new(200, "OK", std::str::from_utf8(exact).unwrap())
            .expect("synthetic response");
        assert_eq!(
            read_json_bounded(response, exact.len(), "test response").unwrap()["ok"],
            true
        );
        let response = ureq::Response::new(200, "OK", std::str::from_utf8(exact).unwrap())
            .expect("synthetic response");
        assert!(read_json_bounded(response, exact.len() - 1, "test response").is_err());
    }

    #[test]
    fn authenticated_agent_rejects_redirect_responses() {
        use std::io::{Read as _, Write as _};
        use std::net::TcpListener;

        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let address = listener.local_addr().unwrap();
        let redirect_target = TcpListener::bind("127.0.0.1:0").unwrap();
        redirect_target.set_nonblocking(true).unwrap();
        let redirect_address = redirect_target.local_addr().unwrap();
        let server = std::thread::spawn(move || {
            let (mut stream, _) = listener.accept().unwrap();
            let mut request = [0_u8; 2048];
            let _ = stream.read(&mut request).unwrap();
            let response = format!(
                "HTTP/1.1 302 Found\r\nLocation: http://{redirect_address}/capture\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
            );
            stream.write_all(response.as_bytes()).unwrap();
        });

        let result = authenticated_agent(HttpPolicy::default())
            .get(&format!("http://{address}/start"))
            .set("x-provider-secret", "synthetic")
            .call();
        let response = result.expect("redirect is returned instead of followed");
        assert_eq!(response.status(), 302);
        server.join().unwrap();
        let err = redirect_target
            .accept()
            .expect_err("redirect target must receive no credential-bearing request");
        assert_eq!(err.kind(), std::io::ErrorKind::WouldBlock);
    }

    #[test]
    fn authenticated_agent_uses_strictest_io_timeout_as_overall_deadline() {
        let policy = HttpPolicy {
            connect_timeout: Duration::from_secs(7),
            read_timeout: Duration::from_secs(2),
            write_timeout: Duration::from_secs(3),
            overall_timeout: Duration::from_secs(5),
        };
        assert_eq!(effective_overall_timeout(policy), Duration::from_secs(2));
        assert_eq!(policy.connect_timeout, Duration::from_secs(7));
    }

    #[test]
    fn authenticated_agent_bounds_slow_response_reads() {
        use std::io::Read as _;
        use std::net::{Shutdown, TcpListener};
        use std::sync::mpsc;
        use std::time::Instant;

        const READ_TIMEOUT: Duration = Duration::from_millis(100);
        const CLIENT_RETURN_DEADLINE: Duration = Duration::from_secs(1);
        const CLEANUP_DEADLINE: Duration = Duration::from_secs(5);

        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let address = listener.local_addr().unwrap();
        let (request_seen_tx, request_seen_rx) = mpsc::channel();
        let (release_server_tx, release_server_rx) = mpsc::channel();
        let server = std::thread::spawn(move || {
            let (mut stream, _) = listener.accept().unwrap();
            stream.set_read_timeout(Some(CLEANUP_DEADLINE)).unwrap();
            let mut request = [0_u8; 2048];
            let request_bytes = stream.read(&mut request).unwrap();
            assert!(request_bytes > 0, "client must send a request");
            request_seen_tx.send(()).unwrap();

            // Keep the response read blocked until the test has observed the
            // client-side timeout. The cleanup deadline prevents a panic in
            // the test thread from leaving this server thread blocked.
            let _ = release_server_rx.recv_timeout(CLEANUP_DEADLINE);
            let _ = stream.shutdown(Shutdown::Both);
        });
        let policy = HttpPolicy {
            connect_timeout: Duration::from_secs(2),
            read_timeout: READ_TIMEOUT,
            write_timeout: Duration::from_secs(2),
            // This deliberately exceeds the assertion deadline so the test
            // fails if the dedicated response/read timeout is removed.
            overall_timeout: CLEANUP_DEADLINE,
        };

        let (client_result_tx, client_result_rx) = mpsc::channel();
        let client = std::thread::spawn(move || {
            let started = Instant::now();
            let result = authenticated_agent(policy)
                .get(&format!("http://{address}/slow"))
                .call();
            client_result_tx.send((started.elapsed(), result)).unwrap();
        });

        let request_seen = request_seen_rx.recv_timeout(CLEANUP_DEADLINE);
        let client_result = request_seen
            .as_ref()
            .map_err(|err| err.to_string())
            .and_then(|_| {
                client_result_rx
                    .recv_timeout(CLIENT_RETURN_DEADLINE)
                    .map_err(|err| err.to_string())
            });

        // Release the intentionally blocked server only after observing the
        // client result (or the assertion deadline), then join both threads.
        let _ = release_server_tx.send(());
        client.join().unwrap();
        server.join().unwrap();

        request_seen.expect("server must receive the local synthetic request");
        let (elapsed, result) = client_result
            .expect("client must enforce the read timeout before the server is released");
        assert!(
            elapsed <= CLIENT_RETURN_DEADLINE,
            "client returned after {elapsed:?}, exceeding {CLIENT_RETURN_DEADLINE:?}"
        );
        let err = result.expect_err("slow response must time out");
        assert!(matches!(err, ureq::Error::Transport(_)));
    }

    // QA13 (step4b-contract-tests-p3a.md §E, 04 §5.5 L880): the pure
    // idempotency-header resolution function's 3 cases — see kcs-adapter unit
    // tests (a)/(b)/(c) in the implementation report.
    #[test]
    fn qa13_http_header_with_token_resolves_the_declared_header() {
        let resolved = resolve_idempotency_header(
            &ProviderIdempotency::HttpHeader("Idempotency-Key".to_owned()),
            Some("intent-token-abc"),
        )
        .unwrap();
        assert_eq!(
            resolved,
            Some(("Idempotency-Key".to_owned(), "intent-token-abc".to_owned()))
        );
    }

    #[test]
    fn qa13_http_header_without_token_is_a_fail_closed_contract_violation() {
        let error = resolve_idempotency_header(
            &ProviderIdempotency::HttpHeader("Idempotency-Key".to_owned()),
            None,
        )
        .unwrap_err();
        assert!(
            matches!(error, AdapterError::ContractViolation(_)),
            "a provider that declares an idempotency key must fail closed when the \
             caller supplies no token, not silently send unauthenticated: {error:?}"
        );
    }

    #[test]
    fn qa13_not_provided_ignores_a_present_token_and_never_errors() {
        // NotProvided must ignore the field entirely — with a token present...
        assert_eq!(
            resolve_idempotency_header(&ProviderIdempotency::NotProvided, Some("intent-token-abc"))
                .unwrap(),
            None
        );
        // ...and with no token, the common real-adapter case (04 §5.5: neither
        // built-in adapter's pinned endpoint offers a provider idempotency key).
        assert_eq!(
            resolve_idempotency_header(&ProviderIdempotency::NotProvided, None).unwrap(),
            None
        );
    }

    #[test]
    fn bounded_reader_rejects_compressed_content_encoding() {
        use std::io::{Read as _, Write as _};
        use std::net::TcpListener;

        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let address = listener.local_addr().unwrap();
        let server = std::thread::spawn(move || {
            let (mut stream, _) = listener.accept().unwrap();
            let mut request = [0_u8; 2048];
            let _ = stream.read(&mut request).unwrap();
            stream
                .write_all(
                    b"HTTP/1.1 200 OK\r\nContent-Encoding: gzip\r\nContent-Length: 2\r\nConnection: close\r\n\r\n{}",
                )
                .unwrap();
        });
        let response = authenticated_agent(HttpPolicy::default())
            .get(&format!("http://{address}/compressed"))
            .call()
            .unwrap();
        let err = read_json_bounded(response, 1024, "test response").unwrap_err();
        assert!(err.to_string().contains("unsupported content encoding"));
        server.join().unwrap();
    }
}
