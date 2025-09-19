# Dojo v2

## Introduction

Dojo V2 transforms conventional Generative Adversarial Network (GAN) into a competitive, decentralized GAN built on the principle of zero-sum incentives. Unlike traditional GAN where the generator simply aims to mimic ground truth data, V2 challenges miners to create outputs that are not only indistinguishable from a high-quality baseline but are also superior to it. This creates a competitive environment where Bittensor miners, acting as both generators and discriminators, are in constant competition to produce and identify the best possible work.

**More detailed info here:** [Dojo V2 Documentation](https://docs.tensorplex.ai/tensorplex-docs/tensorplex-dojo-bittensor-subnet/subnet-mechanism)

## Miner

Miners do not need to spin up any server or code level things to mine! You just need to register to the network, and load your hotkey wallet onto a browser wallet e.g. Talisman and wait to receive tasks.
Start mining at [Testnet](https://testnet.dojo.network) | [Mainnet](https://dojo.network)

```bash
# Register via btcli
btcli s register --netuid 52 # Mainnet
btcli s register --network test --netuid 98
```

## Validator
Please refer the setup guide [here](docs/validator.md).

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
