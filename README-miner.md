## Mining

> **Note:** To connect to testnet, uncomment the testnet related configuration, specifically `NETUID`, `SUBTENSOR_CHAIN_ENDPOINT` and `SUBTENSOR_NETWORK`

### Option 1: Centralised Method

1. Configure .env file

```bash
# Make a copy of .env.example
cp .env.example .env

# Fill envs under 'BITTENSOR ENV VARS' and 'MINER ENV VARS'
# ---------------------------------------------------------------------------- #
#                          BITTENSOR ENV VARS                                  #
# ---------------------------------------------------------------------------- #

BITTENSOR_DIR=$HOME/.bittensor # Your bittensor directory
WALLET_COLDKEY= # Coldkey
WALLET_HOTKEY= # Hotkey

# ---------------------------------------------------------------------------- #
#                          MINER ENV VARS                                      #
# ---------------------------------------------------------------------------- #

# Change to https://dojo-api-testnet.tensorplex.ai for testnet
DOJO_API_BASE_URL="https://dojo-api.tensorplex.ai"
DOJO_API_KEY= # Blank for now
AXON_PORT=8091 # Change if required
```

2. Run the CLI to retrieve API Key and Subscription Key, see [Dojo CLI](#dojo-cli) for usage.

```bash
make dojo-cli

# You can use tab completions to see a list of commands

# Authenticate and generate keys
authenticate
api_key generate
subscription_key generate

# List all keys
api_key list
subscription_key list
```

3. Complete the .env file with the variables below:

```bash
DOJO_API_KEY=# api key from step 2.
```

4. Start the miner by running the following commands:

```bash
make miner-centralised
```

To start with autoupdate for miners (**strongly recommended**), see the [Auto-updater](#auto-updater) section.

### Option 2: Decentralised Method

1. Configure .env file

```bash
# Make a copy of .env.example
cp .env.example .env

# Fill envs under:
# 1: BITTENSOR ENV VARS
# 2: MINER ENV VARS
# 3: MINER DECENTRALIZED ENV VARS
# 4: MINER / VALIDATOR SHARED ENV VARS

# ---------------------------------------------------------------------------- #
#                          BITTENSOR ENV VARS                                  #
# ---------------------------------------------------------------------------- #

BITTENSOR_DIR=$HOME/.bittensor # Your bittensor directory
WALLET_COLDKEY= # Coldkey
WALLET_HOTKEY= # Hotkey

# ---------------------------------------------------------------------------- #
#                          MINER ENV VARS                                      #
# ---------------------------------------------------------------------------- #

DOJO_API_BASE_URL="http://worker-api:8080" # use this value
DOJO_API_KEY= # Blank for now
AXON_PORT=8091 # Change if required

# ---------------------------------------------------------------------------- #
#                          MINER DECENTRALIZED ENV VARS                        #
# ---------------------------------------------------------------------------- #

# For dojo-ui
NEXT_PUBLIC_BACKEND_URL=http://localhost:3000

# For dojo-worker-api
REDIS_USERNAME= # Set a non-default username
REDIS_PASSWORD= # Generate and set a secure password

# AWS credentials for S3
AWS_ACCESS_KEY_ID= # Get from aws
AWS_SECRET_ACCESS_KEY= # Get from aws
AWS_S3_BUCKET_NAME= # Get from aws
S3_PUBLIC_URL= # S3 bucket url that can be accessed publicly

JWT_SECRET= # generate a random JWT key
ETHEREUM_NODE= # get an ethereum endpoint URL from Infura, Alchemy or any other provider

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
```

2. Start the worker api which will be connected to the CLI later.

```bash
make miner-worker-api
```

3. Run the CLI to retrieve API Key and Subscription Key, see [Dojo CLI](#dojo-cli) for usage.

```bash
make dojo-cli
```

4. Grab the API key and add it to your .env file

```bash
DOJO_API_KEY=# api key from earlier
```

5. Now, run the full miner service.

```bash
make miner-decentralised
```

To start with autoupdate for miners (**strongly recommended**), see the [Auto-updater](#auto-updater) section.

> [!IMPORTANT]
>
> Don't be alarmed that the status of the `prisma-setup-miner` service shows exit code 0. This means it ran successfully.
>
> Other services should also be healthy in order for the `miner-testnet-decentralised` service to run successfully.

### Setup Subscription Key for Labellers on UI to connect to Dojo Subnet for scoring

Note: URLs are different for testnet and mainnet. Please refer to [docs](https://docs.tensorplex.ai/tensorplex-docs/tensorplex-dojo-testnet/official-links).

1. Head to https://dojo.tensorplex.ai or https://dojo-testnet.tensorplex.ai and login and sign with your Metamask wallet.

- You'll see an empty homepage with no Tasks, and a "Connect" button on the top right ![image](./assets/ui/homepage.png)
- Click on "Connect" and you'll see a popup with different wallets for you to connect to ![image](./assets/ui/wallet_popup.jpg)
- Click "Next" and "Continue", then finally it will be requesting a signature from your wallet, please sign and it will be connected. ![image](./assets/ui/wallet_sign.jpg)
- Once connected, the top navigation bar should display your wallet address. ![image](./assets/ui/wallet_connected.png)

2. Once connected, please stay connected to your wallet and click on "Enter Subscription Key". ![image](./assets/subscription/enter_subscription.png)

- Give your subscription a name, and enter your subscription key generated earlier before running the miner. _*Refer to step 4 of "Getting Started" if you need to retrieve your key*_ ![image](./assets/subscription/enter_details.png)
- Click "Create" and your subscription will be saved. ![image](./assets/subscription/created_details.png)
- Confirmed your subscription is created properly, and that you can view your tasks! ![image](./assets/subscription/tasks_shown.png)
