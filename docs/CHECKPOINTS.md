# Checkpoints

| Tag | Purpose | Migration | Fixture | Verification | Restore |
|---|---|---|---|---|---|
| `anchor-00-architecture` | Architecture and security baseline | none | none | documentation review | `git switch --detach anchor-00-architecture` |
| `anchor-01-scaffold` | Runnable web/API/worker skeleton | initial | seed-v1 | full check | `git switch --detach anchor-01-scaffold` |
| `anchor-02-domain-api` | Domain model and public API | recorded at tag | pricing-sim-v1 | API and migration tests | `git switch --detach anchor-02-domain-api` |
| `anchor-03-local-inference` | Ollama and NVIDIA adapters | recorded at tag | energy-synthetic-v1 | hardware smoke test | `git switch --detach anchor-03-local-inference` |
| `v0.1.0-user-mvp` | Security-audited user release | recorded at tag | all v1 fixtures | CI, security, E2E | `git switch --detach v0.1.0-user-mvp` |

Tags are annotated and created only from a clean, verified worktree. Runtime data is never restored from Git; migrations and seed commands recreate local state.

