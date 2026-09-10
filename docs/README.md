# Anura — Documentation Index

This directory contains permanent project documentation. Repository-level
documentation lives in the root (`README.md`, `AGENTS.md`, `CONTRIBUTING.md`,
`SECURITY.md`, `CHANGELOG.md`).

## Current documentation

| Document | Status | Purpose |
| --- | --- | --- |
| [history-v1.md](history-v1.md) | **Current / normative** | Extraction History V1: behaviour, storage, settings, UI, limits |
| [dependencies.md](dependencies.md) | **Current / normative** | Python/Flatpak dependency workflow: uv.lock, sync, FEDC/certifi ownership |
| [planning/history-v1-plan.md](planning/history-v1-plan.md) | **Historical** | Pre-implementation History V1 plan (baseline `testing @ a52f4563`); superseded by the merged History V1 integration |

## Structure

```text
docs/
├── README.md              ← this index
├── history-v1.md          ← current History V1 reference (normative)
├── dependencies.md        ← current dependency/CI workflow reference (normative)
├── planning/
│   └── history-v1-plan.md Implementation plan for History V1 (HISTORICAL —
│                            baseline: testing @ a52f4563; superseded by
│                            the merged History V1 work on testing)
└── audit/
    └── legacy/        Historical QA/security audit reports and raw
                       tool outputs (bug hunts, bandit/mypy/ruff/vulture).
                       Kept for historical traceability — do not treat
                       findings as open issues.
```

## Conventions

- Filenames use `kebab-case-lowercase.md`.
- Current/normative feature references live directly under `docs/`.
- Pre-implementation plans belong in `planning/` and are marked historical once implemented.
- Historical audit material belongs in `audit/legacy/` (append-only).
- Agent tooling rules (`.clinerules/`, `CLAUDE.md`) are NOT
  documentation and are not indexed here.
