# Development Standards

## Correctness

- Domain invariants are encoded in types and tested independently of infrastructure.
- Public requests are validated at the API boundary; domain services receive normalized values.
- Money, energy, and carbon use integer micro-units. Floating-point values are presentation-only.
- All timestamps are timezone-aware. SQLite stores UTC.
- Every external call has an explicit timeout and bounded retry policy.

## Interfaces

- FastAPI OpenAPI is the HTTP source of truth; the frontend client is generated from it.
- Additive API fields are preferred within v1. Breaking changes require a versioned route and ADR.
- Error responses use stable machine-readable codes plus a safe user-facing message.

## Quality gates

- Python: Ruff, mypy strict, pytest, pytest-cov.
- TypeScript: strict compiler settings, ESLint, Prettier, Vitest.
- End-to-end: Playwright against the real API with fake infrastructure adapters by default.
- Core domain line coverage must remain at or above 80 percent.

## Logging and privacy

- Structured logs contain correlation IDs, event names, status, duration, and opaque entity IDs.
- Prompts, responses, upload names, authorization data, cookies, and secrets are forbidden.
- Metrics use bounded labels and never include user content or unbounded identifiers.

## Dependencies

- Runtime and development dependencies are locked.
- New dependencies require a license check, maintenance check, and an entry in third-party notices.
- Model weights are installed outside the repository and recorded by immutable digest.

## Git and releases

- Use Conventional Commits and small, reviewable changes.
- Each anchor tag requires a clean worktree and a successful full check.
- Release tags are annotated. Release artifacts include an SBOM and checksums.

