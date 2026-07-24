# Security Policy

## Reporting a vulnerability

**Please do not open a public issue for a security problem.** A public issue
discloses the vulnerability to everyone the moment you file it, including before
there is a fix.

Report privately through either channel:

- **GitHub Security Advisories** — the "Report a vulnerability" button under the
  repository's **Security** tab. This is preferred; it gives us a private thread
  and a place to coordinate a fix.
- **Email** — **tkngtkmrwgnnns@gmail.com** with the subject line
  `Kio security`.

A useful report includes what you did, what happened, what you expected, the
commit or version you tested, and your platform. A minimal reproduction is worth
more than a long description. If you have a proof of concept, please send it
privately rather than publishing it.

## What to expect

Kio is maintained by one person as a pre-release project. Please calibrate your
expectations accordingly:

- **Acknowledgement:** within 7 days. If you have not heard back in that time,
  the message probably got lost — please send a reminder.
- **Assessment:** we will tell you whether we consider it a vulnerability, and
  why, as soon as we have looked at it properly.
- **Fix:** there is no guaranteed timeline. Severity and available time decide.
  We will tell you what we intend to do rather than leave you waiting.

There is **no bug bounty** and no monetary reward. We will credit you in the
advisory and the release notes unless you prefer otherwise.

## Disclosure

Please give us a reasonable chance to ship a fix before publishing. We suggest
90 days from your report, or until a fix is released, whichever comes first. If
you believe the issue is being actively exploited, say so and we will treat it
as urgent.

We would rather you disclose late than never — if we go quiet and stop
responding, publishing is a legitimate thing to do.

## Scope

**In scope:** the code in this repository — the `kio` CLI and the `kio-*`
crates. That includes how Kio handles untrusted input (files it indexes,
adapter responses it parses), how it stores and verifies content-addressed
objects, path handling, and how network approval and secrets are enforced.

**Out of scope:**

- The external services Kio can talk to (Mistral, Google, and others). Report
  those to the provider.
- Findings that require an attacker who already controls the account running
  Kio, or the machine's filesystem.
- Missing hardening with no demonstrated impact — tell us anyway, but as a
  regular issue, not a vulnerability report.

## A note on what this software does

Kio indexes local files and, **only after you explicitly opt in**, can transmit
their contents to external adapters for OCR and embedding. Network transmission
is off by default. If you find a way to make Kio transmit data without that
opt-in, or to a destination other than the approved adapter, we consider that a
serious vulnerability and want to hear about it.

## Prior security work

This repository was reviewed in 2026-07 and the resulting findings were
remediated before publication. The audit artifacts are not published: they
contain working proof-of-concept exploits, and while every finding they describe
was fixed, publishing the exploit set would mostly help someone look for similar
problems. If you are doing security research on Kio and want that context, ask.
