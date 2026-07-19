# Contributing

## Workflow

1. Create a focused branch from `main`.
2. Add or update tests with behavior changes.
3. Run `scripts/check.ps1` and the staged secret scan.
4. Use a Conventional Commit such as `feat(api): add quote expiry validation`.
5. Update `CHANGELOG.md` for user-visible behavior.

## Review gates

- Architecture boundaries and public contracts remain explicit.
- Failure and degradation behavior is tested.
- No unlabelled simulated data appears in the UI or API.
- No sensitive content appears in source, fixtures, snapshots, or logs.
- New dependencies have a compatible license and are listed in `THIRD_PARTY_NOTICES.md`.

