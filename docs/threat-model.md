# Threat Model

## Assets

- User prompts and inference results
- Future provider credentials
- Billing and audit integrity
- Local model and GPU availability
- Public repository history and release artifacts

## Trust boundaries

- Browser to local API
- API to SQLite and artifact storage
- Worker to Ollama
- Worker to NVIDIA telemetry executable
- Local repository to public GitHub

## Principal threats and controls

| Threat | Control |
|---|---|
| Secret committed to Git | Ignore rules, staged and full-history Gitleaks, release checklist, rotation procedure |
| Prompt leakage through logs | Allowlisted structured events, redaction tests, no request-body logging |
| Arbitrary code execution | Structured inference only; no user command, URL, template, or path execution |
| Malicious upload | Size limits, UTF-8 validation, strict CSV/JSONL schema, normalized names |
| Cross-origin request | Loopback bind, exact origin allowlist, trusted hosts, CSP |
| Duplicate execution | Durable lease, idempotency key, state transition checks |
| Falsified green claim | Provenance on every field, simulation banner, immutable fixture version |
| Public data exposure | Repository root isolated from research files; runtime directories ignored and scanned |

## Deferred risks

Authentication, multi-tenant isolation, network deployment, payment, cloud provider credentials, and real VPP commands require a later security review and are not enabled in v0.1.0.

