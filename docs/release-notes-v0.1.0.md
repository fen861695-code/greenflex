# GreenFlex v0.1.0

GreenFlex v0.1.0 delivers a local-first user workflow for open-model text inference with measured model usage, NVIDIA GPU telemetry, simulated flexible pricing, GreenBill, and a content-free Token Passport.

## Highlights

- Manual prompt quoting and sequential local model preview.
- UTF-8 CSV/JSONL batch orders with strict size and field validation.
- Immediate and deadline-aware flexible scheduling against versioned synthetic signals.
- Persistent single-concurrency Worker with leases, retry-once behavior, partial success, and actual Token settlement.
- Gross and idle-baseline-adjusted GPU energy, simulated PUE facility allocation, and location-based carbon estimates.
- Responsive desktop/mobile UI with explicit measured, estimated, and simulated labels.
- Local-only API security controls, content purge, secret-safe logging, CI, CodeQL, Gitleaks, dependency audits, and Dependabot.

## Important boundaries

- Ollama and Qwen2.5 weights are installed separately and are not distributed in this release.
- Price, PUE, electricity price, carbon intensity, renewable share, and green grade are simulated.
- The Token Passport is not an official certification and makes no zero-carbon or market-based claim.
- This unauthenticated release must not be exposed directly to the Internet.

## Verification

- Python: Ruff, mypy, 25 pytest tests, 81.18% coverage, pip-audit.
- Web: ESLint, TypeScript, 10 Vitest tests, 81.5% line coverage.
- E2E: Playwright at 1440x900 and 390x844, no horizontal overflow.
- Hardware: NVIDIA `nvidia-smi` 500 ms sampling verified on an RTX 3060 Laptop GPU.
- Gitleaks 8.30.1: full Git history and tracked release sources passed with zero findings.
- Ollama model smoke test remained pending because GitHub Release Assets were unreachable from the build machine.
