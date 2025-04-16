import argparse
import os
from functools import lru_cache
from pathlib import Path

import bittensor as bt
from dotenv import find_dotenv, load_dotenv

from dojo.logging import logger

base_path = Path.cwd()


def check_config(config: bt.config):
    """Checks/validates the config namespace object."""
    # logger.check_config(config)

    log_dir = str(base_path / "logs")
    full_path = os.path.expanduser(
        f"{log_dir}/{config.wallet.name}/{config.wallet.hotkey}/netuid{config.netuid}/{config.neuron.name}"
    )
    config.neuron.full_path = os.path.expanduser(full_path)
    if not os.path.exists(config.neuron.full_path):
        os.makedirs(config.neuron.full_path, exist_ok=True)


def add_args(parser):
    """
    Adds relevant arguments to the parser for operation.
    """
    # Netuid Arg: The netuid of the subnet to connect to.
    parser.add_argument("--netuid", type=int, help="Subnet netuid", default=52)

    neuron_types = ["miner", "validator"]
    parser.add_argument(
        "--neuron.type",
        choices=neuron_types,
        type=str,
        help="Whether running a miner or validator",
    )
    args, _ = parser.parse_known_args()
    neuron_type = None
    if known_args := vars(args):
        neuron_type = known_args["neuron.type"]

    parser.add_argument(
        "--neuron.name",
        type=str,
        help="Trials for this neuron go in neuron.root / (wallet_cold - wallet_hot) / neuron.name. ",
        default=neuron_type,
    )

    # device = get_device()
    parser.add_argument(
        "--neuron.device", type=str, help="Device to run on.", default="cpu"
    )

    parser.add_argument(
        "--api.port",
        type=int,
        help="FastAPI port for uvicorn to run on, should be different from axon.port as these will serve external requests.",
        default=1888,
    )

    parser.add_argument(
        "--env_file",
        type=str,
        help="Path to the environment file to use.",
    )

    parser.add_argument(
        "--ignore_min_stake",
        action="store_true",
        help="Whether to always include self in monitoring queries, mainly for testing",
    )

    parser.add_argument(
        "--service",
        choices=["miner-decentralised", "miner-centralised", "validator"],
        help="Specify the service to run (miner or validator) for auto_updater.",
    )

    parser.add_argument(
        "--fast_mode",
        action="store_true",
        help="Whether to run in fast mode, for developers to test locally.",
    )

    parser.add_argument(
        "--simulation",
        action="store_true",
        help="Whether to run the validator in simulation mode",
    )

    parser.add_argument(
        "--simulation_bad_miner",
        action="store_true",
        help="Set miner simluation to a bad one",
    )

    epoch_length = 100
    known_args, _ = parser.parse_known_args()
    if known_args := vars(known_args):
        if known_args["fast_mode"]:
            epoch_length = 10

    parser.add_argument(
        "--neuron.epoch_length",
        type=int,
        help="The default epoch length (how often we set weights, measured in 12 second blocks).",
        default=epoch_length,
    )

    if neuron_type == "validator":
        parser.add_argument(
            "--neuron.sample_size",
            type=int,
            help="The number of miners to query per dendrite call.",
            default=8,
        )

        parser.add_argument(
            "--neuron.moving_average_alpha",
            type=float,
            help="Moving average alpha parameter, how much to add of the new observation.",
            default=0.3,
        )

    elif neuron_type == "miner":
        pass


@lru_cache(maxsize=1)
def get_config():
    """Returns the configuration object specific to this miner or validator after adding relevant arguments."""
    parser = argparse.ArgumentParser()
    bt.wallet.add_args(parser)
    bt.subtensor.add_args(parser)
    bt.axon.add_args(parser)
    add_args(parser)

    # Add logging arguments
    bt.logging.add_args(parser)

    # Parse args with config
    config = bt.config(parser)
    check_config(config)

    return config


def source_dotenv():
    """Source env file if provided"""
    config = get_config()
    if config.env_file:
        load_dotenv(find_dotenv(config.env_file), override=True)
        logger.trace(f"Sourcing env vars from {config.env_file}")
        return

    load_dotenv()
