# Checkpoints

| Tag | Commit | Purpose | Migration | Fixture | Start | Verification | Restore |
|---|---|---|---|---|---|---|---|
| `anchor-00-architecture` | `78f64ab` | Architecture and security baseline | none | none | n/a | documentation review | `git switch --detach anchor-00-architecture` |
| `anchor-01-scaffold` | `d188117` | Runnable web/API/worker skeleton | initial | seed-v1 | `scripts/dev.ps1` | full check | `git switch --detach anchor-01-scaffold` |
| `anchor-02-domain-api` | `da2cf2b` | Domain model and public API | `f59417dcb05c` | pricing-sim-v1 | `scripts/dev.ps1` | 20 backend tests, 81.78% coverage | `git switch --detach anchor-02-domain-api` |
| `anchor-03-local-inference` | `ffc6f82` | Ollama, NVIDIA adapters, Worker, and user web app | `f59417dcb05c` | synthetic-cn-east-v1 | `scripts/dev.ps1` | tests, real NVIDIA sample, responsive browser flow; Ollama install blocked by local network | `git switch --detach anchor-03-local-inference` |
| `v0.1.0-user-mvp` | pending | Security-audited user release | pending final tag | all v1 fixtures | `scripts/dev.ps1` | Gitleaks complete; pending real Ollama smoke and GitHub checks | `git switch --detach v0.1.0-user-mvp` |

Tags are annotated and created only from a clean, verified worktree. Runtime data is never restored from Git; migrations and seed commands recreate local state.
