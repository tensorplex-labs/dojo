#!/usr/bin/env bash

set -euo pipefail

sed -i '/^  miner:$/,/^[^[:space:]]/ {
  /image: ghcr.io\/tensorplex-labs\/dojo:main/ s/^/    # /
}' docker-compose.miner.yaml

sed -i '/^    #.*image: ghcr.io\/tensorplex-labs\/dojo:main/a\
    build:\
      context: .\
      dockerfile: docker/Dockerfile' docker-compose.miner.yaml
