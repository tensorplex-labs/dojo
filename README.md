# Dojo v2

Dojo is a Go toolkit for building and running a Bittensor-style subnet stack. It includes a validator node, client SDKs for external services (Kami, Synthetic API, Task API), optional Redis integration, and a scoring pipeline demo.

## Features
- Validator: pulls tasks, queries miners via Kami, scores results, and reports outcomes
- Scoring: configurable pipelines (normalization, cosine similarity, cubic reward) with CLI demo
- Clients: lightweight HTTP clients for Kami, Synthetic API, and Task API
- Utilities: structured logging, Redis helper, chain utils

## Repo layout
- cmd/
  - validator: validator executable
  - scoring: scoring demo CLI
- internal/
  - validator, scoring, kami, syntheticapi, taskapi, synapse, utils, config
- .github/workflows: CI for building binaries and publishing docker images

## Requirements
- Go 1.24.3
- Make
- golangci-lint (for linting)
- lefthook (mandatory; git hooks)
- Redis (optional; validator cache)
- Docker (optional; for container builds)

## Quick start
1) Clone and env
- cp .env.example .env
- Set WALLET_*, NETUID, SUBTENSOR_NETWORK, KAMI_HOST/PORT, SYNTHETIC_API_URL, TASK_API_URL, and Redis vars if used

2) Dev dependencies
- Install golangci-lint (brew install golangci-lint or go install github.com/golangci/golangci-lint/cmd/golangci-lint@latest)
- Install lefthook (brew install lefthook or curl -s https://raw.githubusercontent.com/evilmartians/lefthook/master/install.sh | bash or go install github.com/evilmartians/lefthook@latest)
- Enforce hooks: lefthook install (or make preflight)
- Verify: lefthook run pre-commit

3) Build and run
- make build
- make dev-validator        # run validator with go run
- make run-validator        # run built binary
- make dev-scoring          # run scoring demo

## Validator configuration
Loaded from environment (.env):
- NETUID, SUBTENSOR_NETWORK
- WALLET_COLDKEY, WALLET_HOTKEY, BITTENSOR_DIR
- KAMI_HOST, KAMI_PORT
- REDIS_HOST, REDIS_PORT, REDIS_PASSWORD, REDIS_DB (optional)
- OPENROUTER_API_KEY, SYNTHETIC_API_URL
- TASK_API_URL

## Common tasks
- deps: make deps
- format: make fmt
- vet: make vet
- lint: make lint
- tests: make test
- all checks: make check (runs preflight automatically)

## Git hooks (required)
This repo uses lefthook to enforce quality gates:
- pre-commit: make fmt, make vet, make lint
- pre-push: go test ./...
Install and keep it current:
- make preflight
- lefthook install -f    # force reinstall if hooks don’t run
- git config --get core.hooksPath (should be unset for default)

## Docker & CI
- CI builds Go binaries for matrix-defined platforms
- On successful build, docker images are built and published to ghcr.io/<owner>/<repo>/<app>

## Troubleshooting
- Hooks not running: run lefthook install -f, then lefthook run pre-commit
- golangci-lint missing: install as above
- Redis optional: validator starts without it but logs a warning
