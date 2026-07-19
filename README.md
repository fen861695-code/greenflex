# GreenFlex

GreenFlex is a local-first green inference ordering platform. Users can preview open models, submit batch text inference jobs, compare immediate and flexible simulated prices, and receive measured GPU energy records plus an auditable Token Passport.

> Status: architecture baseline. The user MVP is under active development.

## Data truth boundary

- **Measured:** local model output, token counts, latency, and NVIDIA GPU board power when telemetry is available.
- **Estimated:** facility energy derived from measured GPU energy and an explicitly versioned PUE assumption.
- **Simulated:** electricity price, grid carbon intensity, renewable share, service prices, discounts, and green grades.

GreenFlex does not claim zero-carbon inference, government certification, or provider-side cloud energy measurement.

## Planned local stack

- React + TypeScript user application
- FastAPI modular monolith and persistent worker
- SQLite with Alembic migrations
- Ollama with Qwen2.5 0.5B, 1.5B, and 3B models
- NVIDIA telemetry through `nvidia-smi`

See [ARCHITECTURE.md](ARCHITECTURE.md), [SECURITY.md](SECURITY.md), and [docs/development-standards.md](docs/development-standards.md) before contributing.

## License

Source code is licensed under Apache-2.0. Model weights, datasets, and third-party components retain their own licenses and are not redistributed by this repository.

