# Validator Docs

## Validator Setup

1. Clone `scores_example.json` to `scores.json`

```bash
cp scores_example.json scores.json
```

2. Clone `.env.example` to `.env`

```bash
# Copy the .env.exmaple to .env
cp .env.example .env
```

3.  Edit the following!

```bash
BITTENSOR_DIR=~/.bittensor
WALLET_COLDKEY=YOUR_COLDKEY_NAME
WALLET_HOTKEY=YOUR_HOTKEY_NAME

NETUID=52 # 98 for testnet

SUBTENSOR_NETWORK=ws://mainnet-lite-amd64:9944 # optional: replace with your custom node or `test` for testnet or finney for mainnet

REDIS_HOST=redis
REDIS_PORT=6379
REDIS_USERNAME=YOUR_REDIS_USERNAME
REDIS_PASSWORD=YOUR_REDIS_PASSWORD
REDIS_DB=0

OPENROUTER_API_KEY=YOUR_OPENROUTER_KEY # https://openrouter.ai

# You can leave the langfuse value as is, if you do not want to see the logging trace of the llm calls
LANGFUSE_SECRET_KEY=
LANGFUSE_PUBLIC_KEY=
LANGFUSE_HOST="https://us.cloud.langfuse.com" # 🇺🇸 US region

DOJO_LOKI_URL= # DOJO TEAM WILL PROVIDE
VALIDATOR_HOTKEY=YOUR_VALIDATOR_HOTKEY
```

4. OPTIONAL: Start the local subtensor node

```bash
# Start the compose for subtensor base on your machine architecture type
docker compose -f  docker-compose.subtensor.yaml up -d [mainnet-lite-<amd64|arm64> | testnet-lite-<amd64|arm64>]

# e.g. for amd64
docker compose -f  docker-compose.subtensor.yaml up -d mainnet-lite-amd64
```

5. Pull loki plugin and start the compose stack

```bash
# Pull loki plugin
docker plugin install grafana/loki-docker-driver:3.3.2-amd64 --alias loki --grant-all-permissions

# Start the compose stack
docker compose up -d
```

## Manual weights setting guide (NOTE: please configure the .env properly as mentioned above first!)

```bash
# Ensure kami is running
docker compose up -d kami

# Run the cli, it should be building wiht the Dockerfile-cli file
docker compose -f docker-compose.cli.yaml run --rm cli

# Select the desired choice either set 100% burn weights to our owner UID 158 or set weights based on the scores.json file
```
