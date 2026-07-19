# Checkpoints

| Tag | Purpose | Migration | Fixture | Verification | Restore |
|---|---|---|---|---|---|
| `anchor-00-architecture` | Architecture and security baseline | none | none | documentation review | `git switch --detach anchor-00-architecture` |
| `anchor-01-scaffold` | Runnable web/API/worker skeleton | initial | seed-v1 | full check | `git switch --detach anchor-01-scaffold` |
| `anchor-02-domain-api` | Domain model and public API | `f59417dcb05c` | pricing-sim-v1 | 20 backend tests, 81.78% coverage | `git switch --detach anchor-02-domain-api` |
| `anchor-03-local-inference` | Ollama, NVIDIA adapters, Worker, and user web app | `f59417dcb05c` | synthetic-cn-east-v1 | tests, real NVIDIA sample, responsive browser flow; Ollama install blocked by local network | `git switch --detach anchor-03-local-inference` |
| `v0.1.0-user-mvp` | Security-audited user release | recorded at tag | all v1 fixtures | CI, security, E2E | `git switch --detach v0.1.0-user-mvp` |

Tags are annotated and created only from a clean, verified worktree. Runtime data is never restored from Git; migrations and seed commands recreate local state.
