# Project Rules for Coding Agents

1. Read `ARCHITECTURE.md`, `SECURITY.md`, and `docs/development-standards.md` before editing.
2. Preserve the modular-monolith boundaries. Domain code cannot import FastAPI, SQLAlchemy, Ollama, or NVIDIA adapters.
3. Never place prompts, responses, credentials, cookies, authorization headers, or user files in logs, metrics, Passports, fixtures, screenshots, or commits.
4. Every energy, carbon, price, green-share, or grade field must declare `measured`, `estimated`, or `simulated` provenance.
5. Do not add arbitrary shell execution, user-controlled model paths, URLs, templates, or filesystem paths.
6. Public API changes require OpenAPI regeneration, frontend type updates, tests, and an ADR when compatibility changes.
7. Database migrations require both upgrade and downgrade paths.
8. Use Conventional Commits. Run `scripts/check.ps1` before an anchor or release tag.
9. Never commit runtime databases, uploads, outputs, telemetry, logs, model weights, `.env`, or generated credentials.
10. Do not claim zero carbon, official certification, real electricity prices, or real VPP revenue in v0.1.0.

