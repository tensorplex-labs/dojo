<div align="center">
  <img src="./assets/dojo.png" alt="Dojo Logo" width="300">
  <h1 style="border-bottom: 0">Dojo Subnet</h1>
</div>

<div align="center">
  <a href="https://discord.gg/p8tg26HFQQ">
    <img src="https://img.shields.io/discord/1186416652955430932.svg" alt="Discord">
  </a>
  <a href="https://opensource.org/license/MIT">
    <img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT">
  </a>
</div>

<br>

<div align="center">
  <a href="https://www.tensorplex.ai/">Website</a>
  ·
  <a href="https://docs.tensorplex.ai/tensorplex-docs/tensorplex-dojo-testnet">Docs</a>
  ·
  <a href="https://docs.tensorplex.ai/tensorplex-docs/tensorplex-dojo-testnet/whitepaper">Whitepaper</a>
  ·
  <a href="https://huggingface.co/tensorplex-labs">HuggingFace</a>
  ·
  <a href="#getting-started">Getting Started</a>
  ·
  <a href="https://twitter.com/TensorplexLabs">Twitter</a>
</div>

---

<details>
<summary>Table of Contents</summary>

- [Introduction](#introduction)
  - [Benefits to participants contributing through Dojo](#benefits-to-participants-contributing-through-dojo)
- [Prerequisites](#prerequisites)
  - [Validator](#validator)
    - [Required Software](#required-software)
    - [System Requirements](#system-requirements)
  - [Miner](#miner)
    - [Required Software](#required-software-1)
    - [System Requirements](#system-requirements-1)
- [Getting Started](#getting-started)
  - [For Miners](#for-miners)
  - [For Validators](#for-validators)
- [Auto-updater](#auto-updater)
- [For Dojo developers](#for-dojo-developers)
  - [Dataset Extraction](#dataset-extraction)
- [License](#license)

</details>

---

# Introduction

The development of open-source AI models is often hindered by the lack of high-quality human-generated datasets. Closed-source AI developers, aiming to reduce data collection costs, have created significant social and economic equity challenges, with workers being paid less than $2 per hour for mentally and emotionally taxing tasks. The benefits of these models have been concentrated among a select few, exacerbating inequalities among contributors.

Enter Tensorplex Dojo Subnet — an open platform designed to crowdsource high-quality human-generated datasets. Powered by Bittensor, the Dojo Subnet addresses these challenges by allowing anyone to earn TAO by labeling data or providing human-preference data. This approach democratizes the collection of human preference data, addressing existing equity issues and paving the way for more inclusive and ethical AI development.

Key Features

To ensure the quality and integrity of the data collected, Dojo introduces several novel features:

- Synthetic Task Generation: Unique tasks are generated by state-of-the-art Large Language Models (LLMs) to collect human feedback data, which can be used to improve open-source models.
- Synthetic Ground Truth Validation Mechanism: Validators can synthetically generate partial ground truths, allowing them to determine the quality of responses provided by individual participants.
- Obfuscation: Techniques to prevent sybil attacks and ensure contributions are genuinely human.

Use Cases

The Dojo Subnet offers multiple use cases:

- Synthetically Generated Tasks: These tasks can bootstrap the human participant pool and can be used for model training or fine-tuning from the outset.
- Cross-subnet Validation: Validators can use responses to rate the quality of outputs across other Bittensor subnets, thereby incentivizing miners to improve their performance.
- External Data Acquisition: Entities outside the Bittensor ecosystem can tap into the subnet to acquire high-quality human-generated data.

By creating an open platform for gathering human-generated datasets, Tensorplex Dojo Subnet aims to solve the challenges of quality control, human verification, and sybil attack prevention while promoting a more equitable distribution of benefits in AI development.

## Benefits to participants contributing through Dojo

- Open platform: Anyone capable can contribute, ensuring broad participation and diverse data collection.

- Flexible work environment: Participants enjoy the freedom to work on tasks at their convenience from any location.

- Quick payment: Rewards are streamed consistently to participants, as long as they complete sufficient tasks within a stipulated deadline and have them accepted by the subnet.

<br>

# Prerequisites

## Validator

### Required Software

- pm2
- docker
- GNU make
- openrouter api key

### System Requirements

- 4 cores
- 16 GB RAM
- 2TB SSD

## Miner

### Required Software

- pm2
- docker
- GNU make

### System Requirements

- 2 cores
- 8 GB RAM
- 32GB SSD or 1TB SSD if decentralised

# Getting Started

> [!IMPORTANT]
>
> This setup guide uses specific tools to ensure a smooth installation process:
>
> - [fnm](https://github.com/Schniz/fnm) for managing Node.js & npm versions (required for PM2)
> - [Docker](https://docs.docker.com/engine/install/) and [Docker Compose](https://docs.docker.com/compose/)
> - [Conda](https://docs.anaconda.com/miniconda/#quick-command-line-install) for using the auto-updater for validators or miners, this is recommended but you may use any python environment provider of choice.

> Please ensure these prerequisites are installed on your system before proceeding with the installation steps, these are needed by both **validators and miners**.

1. Clone the project, set up and configure python virtual environment

```bash
# In this guide, we will utilize the ~/opt directory as our preferred location.
cd ~/opt

# Clone the project
git clone https://github.com/tensorplex-labs/dojo.git
cd dojo/

# setup conda env using miniconda, and follow the setup
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O ~/miniconda3/miniconda.sh
bash ~/miniconda3/miniconda.sh -b -u -p ~/miniconda3
# verify conda installation
conda info
# create python env and install dependencies
conda create -n dojo_py311 python=3.11
conda activate dojo_py311
make install
```

2. Install PM2, one way is through fnm

```bash
# for linux, a convenience script is available
./dojo/scripts/setup/install_pm2.sh

# for mac/linux (if you do not trust the bash script)
curl -fsSL https://fnm.vercel.app/install | bash
# for windows, choose 1 of the following,
# based on https://github.com/Schniz/fnm?#manually
cargo install fnm
choco install fnm
scoop install fnm
winget install Schniz.fnm

# run any post-install shell setup scripts
# based on https://github.com/Schniz/fnm?#shell-setup

# assuming we are using zsh
echo 'eval "$(fnm env --use-on-cd --shell zsh)"' >> ~/.zshrc
# you can tell what shell you're using by running:
echo $0

# verify fnm installation
fnm --version

# get npm & node, and verify npm installation
fnm install lst/iron && npm --version

# install pm2 and verify installation
npm install -g pm2 && pm2 --version
```

3. Install Docker & Docker Compose

For Docker installation, see https://docs.docker.com/engine/install/ for instructions

For Docker Compose installation, see https://docs.docker.com/compose/install/linux for instructions

```bash
# For linux, a convenience script is available
./dojo/scripts/setup/install_docker.sh

# Verify both docker and docker compose are installed
docker --version
docker compose version

# Validators, install docker loki plugin
docker plugin install grafana/loki-docker-driver:3.3.2-amd64 --alias loki --grant-all-permissions
```

4. Start local subtensor node (**optional**)
   > The included subtensor service only exposes 30333 (p2p) to the public, 9933 and 9944 are only accessible internally in the docker network, feel free to change the configuration if required.

```bash
# Mainnet
make subtensor-mainnet

# Testnet
make subtensor-testnet
```

5. Create your wallets if they aren't created yet

```bash
# run btcli
make btcli
# create your wallets
btcli wallet new_coldkey
btcli wallet new_hotkey
```

6. Get some TAO and ensure you have enough TAO to cover the registration cost

```bash
# for Testnet
# If using local subtensor, use ws://mainnet-lite:9944 (mainnet) or ws://testnet-lite:9944 (testnet)
btcli s list --subtensor.network test

# Output from the `btcli s list ...` command
NETUID    N    MAX_N   EMISSION  TEMPO  RECYCLE        POW       SUDO
 0      128   128.00   0.00%     10    τ1.00000     10.00 M     5C4hrfjw9DjXZTzV3MwzrrAr9P1MJhSrvWGWqi1eSuyUpnhM
...
 98     17    256.00   0.00%     360   τ0.00001  18446744.07 T  5GTAfh3YTcokxWdGc3DgLV5y3hHB4Bs5PQGqw9fEn1WrcwWP
...
```

> [!NOTE]
> the "RECYCLE" column represents the subnet registration cost

7. Register to our subnet

```bash
# run the dockerized btcli
make btcli
# register your wallet to our subnet
# If using local subtensor, use ws://mainnet-lite:9944 (mainnet) or ws://testnet-lite:9944 (testnet)

# Mainnet
btcli s register --wallet.name coldkey --wallet.hotkey hotkey --netuid 52 --subtensor.network finney
# Testnet
btcli s register --wallet.name coldkey --wallet.hotkey hotkey --netuid 98 --subtensor.network test
```

## [For Miners](README-miner.md)

## [For Validators](README-validator.md)

# Auto-updater

> [!WARNING]
> Please ensure that you stop the pm2 process while you are modifying the validator/miner code to avoid any unexpected code reverts, as the auto updater will stash your changes before pulling from the remote origin.

To start with the auto update for validators or miners, (**strongly recommended**):

Please ensure that you run the command in the python environment, if you haven't configured the python environment yet see Step 1 of [Getting Started](#getting-started).

```bash
# activate python env
conda activate dojo_py311

# validator
pm2 start auto_update.py --name auto-update-validator --interpreter $(which python3) -- ---service validator

# miner
pm2 start auto_update.py --name auto-update-miner-centralised --interpreter $(which python3) -- --service miner

```

# For Dojo developers

You most likely won't be running a dockerized version of the subnet code as you ship. Use the following guide to get up and running

1. Get uv or miniconda or whatever choice of backend. Here, we'll assume you're using uv.

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

2. Make sure you have a python version >=3.10

```bash
uv python list
```

3. Create a virtualenv

```bash
# i'm using 3.11 here, but you may use any >=3.10 version
uv venv dojo_venv --python=$(uv python find 3.11)
```

4. Activate virtualenv

```bash
# follows python-venv syntax
source dojo_venv/bin/activate
```

5. Install our dependencies

```bash
# install dev dependencies
make install-dev
# install test dependencies
make install-test
```

## Dataset Extraction

The dataset should be in different parts, currently `MAX_CHUNK_SIZE_MB` is set to 50MB on the dataset service, due to limitations on the load balancer. Use the commands to combine all into a single dataset file:

```bash
aws s3 cp s3://amzn-s3-demo-bucket1/ <PATH_ON_LOCAL> --recursive --exclude "*" --include "hotkey_<vali_hotkey>_dataset_20250212*.jsonl"
cd <PATH_ON_LOCAL>
# to merge all chunks into a single dataset file
cat *.jsonl > hotkey_<vali_hotkey>_dataset_combined.jsonl
```

# License

This repository is licensed under the MIT License.

```text
# The MIT License (MIT)
# Copyright © 2023 Yuma Rao

# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
# documentation files (the "Software"), to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all copies or substantial portions of
# the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO
# THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# DEALINGS IN THE SOFTWARE.
```
