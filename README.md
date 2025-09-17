# Dojo v2

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

1. Clone `.env.example` to `.env`

```bash
# Copy the .env.exmaple to .env
cp .env.example .env

# Edit the following!
BITTENSOR_DIR=~/.bittensor
WALLET_COLDKEY=YOUR_COLDKEY_NAME
WALLET_HOTKEY= YOUR_HOTKEY_NAME


NETUID=52 # 98 for testnet

SUBTENSOR_NETWORK=finney # optional: replace with your custom node or `test` for testnet

OPENROUTER_API_KEY=YOUR_OPENROUTER_KEY

TASK_API_URL=https://dojo.network/api/v1/ # testnet: https://dev.dojo.network/api/v1
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
