# Security Policy

## Supported version

Security fixes target the latest tagged release. The local-only v0.1.0 MVP is not approved for direct Internet exposure.

## Reporting

After the public GitHub repository is created, use GitHub Private Vulnerability Reporting. Do not open a public issue containing a vulnerability, credential, prompt, response, or user artifact.

## Secret handling

- Secrets are server-side environment variables only.
- `.env` files, databases, uploads, result artifacts, telemetry, logs, and model weights are excluded from Git.
- Frontend variables prefixed with `VITE_` are public and must never contain secrets.
- Logs use an allowlist and redact token, key, secret, authorization, cookie, and password fields.

## Leak response

1. Revoke and rotate the credential immediately.
2. Disable affected integrations and assess access logs.
3. Remove the secret from Git history and release artifacts.
4. Re-run full-history secret scanning.
5. Document the incident without reproducing the secret.

Deleting a file or commit is not sufficient if the credential has not been revoked.

