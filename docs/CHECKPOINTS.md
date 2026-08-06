# Checkpoints

| Tag | Commit | Purpose | Migration | Fixture | Start | Verification | Restore |
|---|---|---|---|---|---|---|---|
| `anchor-00-architecture` | `78f64ab` | Architecture and security baseline | none | none | n/a | documentation review | `git switch --detach anchor-00-architecture` |
| `anchor-01-scaffold` | `d188117` | Runnable web/API/worker skeleton | initial | seed-v1 | `scripts/dev.ps1` | full check | `git switch --detach anchor-01-scaffold` |
| `anchor-02-domain-api` | `da2cf2b` | Domain model and public API | `f59417dcb05c` | pricing-sim-v1 | `scripts/dev.ps1` | 20 backend tests, 81.78% coverage | `git switch --detach anchor-02-domain-api` |
| `anchor-03-local-inference` | `ffc6f82` | Ollama, NVIDIA adapters, Worker, and user web app | `f59417dcb05c` | synthetic-cn-east-v1 | `scripts/dev.ps1` | tests, real NVIDIA sample, responsive browser flow; Ollama install blocked by local network | `git switch --detach anchor-03-local-inference` |
| `v0.1.0-user-mvp` | annotated tag target | Security-audited user release | `f59417dcb05c` | all v1 fixtures | `scripts/dev.ps1` | full local checks, real NVIDIA telemetry, Ollama plus all three Qwen2.5 models, GreenFlex preview, and required GitHub checks | `git switch --detach v0.1.0-user-mvp` |

Tags are annotated and created only from a clean, verified worktree. The release row resolves to an exact commit with `git rev-list -n 1 v0.1.0-user-mvp`; a literal self-referential commit hash cannot be embedded in that same commit. Runtime data is never restored from Git; migrations and seed commands recreate local state.
| `anchor-04-green-router` | (pending) | GreenRouter v1 smart model routing | `a7c3f9d2e1b0` | model-catalog-v2, synthetic-cn-east-v2 | `scripts/dev.ps1` | recommendation tests, 4-mode UI, audit logging | `git switch --detach anchor-04-green-router` |
