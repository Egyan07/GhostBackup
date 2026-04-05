# Security Policy

## Supported Versions

| Version | Support Level       |
| ------- | ------------------- |
| 3.4.x   | Full support        |
| 3.3.x   | Security fixes only |
| < 3.3   | Unsupported         |

## Reporting a Vulnerability

If you discover a security vulnerability in GhostBackup, please report it
responsibly:

1. **GitHub Issues** -- Open an issue at
   https://github.com/Egyan07/GhostBackup/issues with the label `security`.
   Describe the affected component and the general nature of the issue.
   **Do not include exploit code, proof-of-concept payloads, or step-by-step
   reproduction details in the public issue.**

2. **Email** -- For sensitive reports that should not be public, contact the
   maintainer directly at the email address listed on the
   [Egyan07 GitHub profile](https://github.com/Egyan07).

## What to Expect

- Acknowledgement of your report within **48 hours**.
- An initial assessment and severity rating within **5 business days**.
- A fix or mitigation released within **30 days** for confirmed vulnerabilities,
  depending on complexity. Critical issues will be prioritised.
- Credit in the release notes, unless you prefer to remain anonymous.

## Scope

The following are considered valid security issues:

- Weaknesses in AES-256-GCM encryption or key handling
- Authentication or authorisation bypass on the localhost API
- Path traversal allowing access to files outside the backup scope
- Content Security Policy (CSP) bypass in the Electron renderer
- Credential or key material leakage (logs, temp files, memory dumps)
- Remote code execution via crafted backup archives or API input

The following are **out of scope**:

- Denial of service against the localhost-only FastAPI server
- Attacks that require prior physical access to the machine
- Social engineering of end users
- Vulnerabilities in third-party dependencies with no demonstrated impact on
  GhostBackup

## Security Audit Status

This project has **not** undergone an external or third-party security audit.
The encryption and API surface have been reviewed by the maintainer only.
If you are a security researcher interested in auditing GhostBackup,
please get in touch.

## Architecture Notes

GhostBackup is a Windows desktop application built with Electron, React, and a
FastAPI backend. The API binds exclusively to `127.0.0.1` and is not intended
to be network-accessible. All backup encryption uses AES-256-GCM.
