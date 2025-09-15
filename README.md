# Dojo v2

Dojo is a Go toolkit for building and running a Bittensor-style subnet stack. It includes a validator node, client SDKs for external services (Kami, Synthetic API, Task API), optional Redis integration, and a scoring pipeline demo.

## Incentives Mechanism

## Miner

Miners do not need to spin up any server or code level things to mine! You just need to register to the network, and load your hotkey wallet onto a browser wallet e.g. Talisman and wait to receive tasks.
Start mining at [Testnet](https://testnet.dojo.network) | [Mainnet](https://dojo.network)

## Validator

### Requirements

- Go 1.24.3
- Make
- golangci-lint (for linting)
- lefthook (mandatory; git hooks)
- Redis (optional; validator cache)
- Docker (optional; for container builds)

### Validator Guide

1. Clone and env

```bash
# Copy the .env.exmaple to .env
cp .env.example .env

# Edit the following!
BITTENSOR_DIR=~/.bittensor
WALLET_COLDKEY=YOUR_COLDKEY_NAME
WALLET_HOTKEY= YOUR_HOTKEY_NAME

KAMI_HOST=kami
KAMI_PORT=8882

NETUID=98 # 52 for mainnet

SUBTENSOR_NETWORK=wss://test.finney.opentensor.ai:443 # mainnet

REDIS_HOST=redis
REDIS_PORT=6379
REDIS_USERNAME=YOUR_REDIS_USERNAME
REDIS_PASSWORD=YOUR_REDIS_PASSWORD
REDIS_DB=0

OPENROUTER_API_KEY=YOUR_OPENROUTER_KEY
SYNTHETIC_API_URL=http://synthetic-api:5003/

LANGFUSE_SECRET_KEY=
LANGFUSE_PUBLIC_KEY=
LANGFUSE_HOST="https://us.cloud.langfuse.com" # 🇺🇸 US region

TASK_API_URL=http://dojo.network/api/v1/

ENVIRONMENT=production # Can be dev | test | prod. Difference being the intervals!
```

2. Start the compose stack

```bash
docker compose up -d
```

## Development

### Git hooks (required)

This repo uses lefthook to enforce quality gates:

- pre-commit: make fmt, make vet, make lint
- pre-push: go test ./...
  Install and keep it current:
- make preflight
- lefthook install -f # force reinstall if hooks don’t run
- git config --get core.hooksPath (should be unset for default)

### Docker & CI

- CI builds Go binaries for matrix-defined platforms
- On successful build, docker images are built and published to ghcr.io/<owner>/<repo>/<app>

### Troubleshooting

- Hooks not running: run lefthook install -f, then lefthook run pre-commit
- golangci-lint missing: install as above
- Redis optional: validator starts without it but logs a warning

### Common tasks

- deps: make deps
- format: make fmt
- vet: make vet
- lint: make lint
- tests: make test
- all checks: make check (runs preflight automatically)
