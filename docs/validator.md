
# Validator Setup

1. Clone `.env.example` to `.env`

```bash
# Copy the .env.exmaple to .env
cp .env.example .env
```

2.  Edit the following!

```bash
BITTENSOR_DIR=~/.bittensor
WALLET_COLDKEY=YOUR_COLDKEY_NAME
WALLET_HOTKEY=YOUR_HOTKEY_NAME

NETUID=52 # 98 for testnet

SUBTENSOR_NETWORK=finney # optional: replace with your custom node or `test` for testnet

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

3. Start the compose stack

```bash
docker compose up -d
```
