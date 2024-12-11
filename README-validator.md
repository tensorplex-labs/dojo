## Validating

> **Note:** To connect to testnet, uncomment the testnet related configuration, specifically `NETUID`, `SUBTENSOR_CHAIN_ENDPOINT` and `SUBTENSOR_NETWORK`

Copy the validator .env file and set up the .env file

```bash
# Copy .env.validator.example
cp .env.validator.example .env.validator

# Fill envs under:
# 1: BITTENSOR ENV VARS
# 2: VALIDATOR ENV VARS
# 3: MINER / VALIDATOR SHARED ENV VARS

# ---------------------------------------------------------------------------- #
#                          BITTENSOR ENV VARS                                  #
# ---------------------------------------------------------------------------- #

BITTENSOR_DIR=$HOME/.bittensor # Your bittensor directory
WALLET_COLDKEY= # Coldkey
WALLET_HOTKEY= # Hotkey

# ---------------------------------------------------------------------------- #
#                     MINER / VALIDATOR SHARED ENV VARS                        #
# ---------------------------------------------------------------------------- #

DB_HOST=postgres:5432
DB_NAME=db
DB_USERNAME= # Set a non-default username
DB_PASSWORD= # Generate and set a secure password
DATABASE_URL=postgresql://${DB_USERNAME}:${DB_PASSWORD}@${DB_HOST}/${DB_NAME}

REDIS_HOST=redis
REDIS_PORT=6379
REDIS_DB=0

# ---------------------------------------------------------------------------- #
#                          VALIDATOR ENV VARS                                  #
# ---------------------------------------------------------------------------- #

# Head to https://wandb.ai/authorize to get your API key
WANDB_API_KEY="<wandb_key>"
WANDB_PROJECT_NAME=dojo-mainnet

# For dojo-synthetic-api
OPENROUTER_API_KEY="sk-or-v1-<KEY>"
SYNTHETIC_API_URL=http://synthetic-api:5003

# Langfuse free tier is more than enough
LANGFUSE_SECRET_KEY=# head to langfuse.com
LANGFUSE_PUBLIC_KEY=# head to langfuse.com
LANGFUSE_HOST="https://us.cloud.langfuse.com" # 🇺🇸 US region

# Other LLM API providers, Optional or if you've chosen it over Openrouter
TOGETHER_API_KEY=
OPENAI_API_KEY=
```

> **Note:** To ensure your validator runs smoothly, enable the auto top-up feature for Openrouter, this ensures that your validator will not fail to call synthetic API during task generation. The estimate cost of generating a task is approximately $0.20 USD.

Start the validator

```bash
# To start the validator:
make validator
```

To start with autoupdate for validators (**strongly recommended**), see the [Auto-updater](#auto-updater) section.