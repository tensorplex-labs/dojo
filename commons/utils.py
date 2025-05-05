import os
import time
import uuid
from datetime import datetime, timedelta, timezone

import bittensor as bt
import numpy as np
import plotext
from loguru import logger

from commons.objects import ObjectManager
from dojo.kami import SubnetMetagraph

ROOT_WEIGHT = 0.18
ROOT_NETUID = 0


class aobject:
    """Inheriting this class allows you to define an async __init__.

    So you can create objects by doing something like `await MyClass(params)`
    """

    async def __new__(cls, *a, **kw):
        instance = super().__new__(cls)
        await instance.__init__(*a, **kw)
        return instance

    async def __init__(self):
        pass


def get_effective_stake(hotkey: str, subtensor: bt.subtensor) -> float:
    if isinstance(subtensor, bt.AsyncSubtensor):
        raise NotImplementedError("Async subtensor not supported")

    root_stake = 0
    try:
        root_metagraph = subtensor.metagraph(ROOT_NETUID)
        root_stake = root_metagraph.S[root_metagraph.hotkeys.index(hotkey)].item()
    except (ValueError, IndexError):
        logger.trace(
            f"Hotkey {hotkey} not found in root metagraph, defaulting to 0 root_stake"
        )

    alpha_stake = 0
    try:
        config = ObjectManager.get_config()
        subnet_metagraph = subtensor.metagraph(netuid=config.netuid)  # type:ignore
        alpha_stake = subnet_metagraph.alpha_stake[
            subnet_metagraph.hotkeys.index(hotkey)
        ]
    except (ValueError, IndexError):
        logger.trace(
            f"Hotkey {hotkey} not found in subnet metagraph for netuid: {subnet_metagraph.netuid}, defaulting to 0 alpha_stake"
        )

    effective_stake = (root_stake * ROOT_WEIGHT) + alpha_stake

    return effective_stake


# TODO: use this function everywhere instead of also having a second function
def aget_effective_stake(hotkey: str, subnet_metagraph: SubnetMetagraph) -> float:
    # With runtime api, you do not need to query root metagraph, you can just get it from the subnet itself.
    idx = subnet_metagraph.hotkeys.index(hotkey)

    root_stake = 0
    try:
        root_stake = subnet_metagraph.taoStake[idx]
    except (ValueError, IndexError):
        logger.trace(
            f"Hotkey {hotkey} not found in root metagraph, defaulting to 0 root_stake"
        )

    alpha_stake = 0
    try:
        alpha_stake = subnet_metagraph.alphaStake[idx]
    except (ValueError, IndexError):
        logger.trace(
            f"Hotkey {hotkey} not found in subnet metagraph for netuid: {subnet_metagraph.netuid}, defaulting to 0 alpha_stake"
        )

    effective_stake = (root_stake * ROOT_WEIGHT) + alpha_stake

    return effective_stake


def _terminal_plot(
    title: str, y: np.ndarray, x: np.ndarray | None = None, sort: bool = False
):
    """Plot a scatter plot on the terminal.
    It is crucial that we don't modify the original order of y or x, so we make a copy first.

    Args:
        title (str): Title of the plot.
        y (np.ndarray): Y values to plot.
        x (np.ndarray | None, optional): X values to plot. If None, will use a np.linspace from 0 to len(y).
        sort (bool, optional): Whether to sort the y values. Defaults to False.
    """
    if x is None:
        x = np.linspace(0, len(y), len(y) + 1)

    if sort:
        y_copy = np.copy(y)
        y_copy.sort()
        y = y_copy

    # plot actual points first
    plotext.scatter(x, y, marker="bitcoin", color="orange")  # show the points exactly
    plotext.title(title)
    plotext.ticks_color("red")
    plotext.xfrequency(1)  # Set frequency to 1 for better alignment
    plotext.xticks(x)  # Directly use x for xticks
    plotext.ticks_style("bold")
    plotext.grid(horizontal=True, vertical=True)
    plotext.plotsize(
        width=int(plotext.terminal_width() * 0.95),
        height=int(plotext.terminal_height() * 0.95),
    )
    plotext.canvas_color(color=None)
    plotext.theme("clear")

    plotext.show()
    plotext.clear_figure()


def get_new_uuid():
    return str(uuid.uuid4())


def get_epoch_time():
    return time.time()


def datetime_as_utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc)


def datetime_to_iso8601_str(dt: datetime) -> str:
    return dt.replace(tzinfo=timezone.utc).isoformat()


def iso8601_str_to_datetime(dt_str: str) -> datetime:
    return datetime.fromisoformat(dt_str).replace(tzinfo=timezone.utc)


def loaddotenv(varname: str):
    """Wrapper to get env variables for sanity checking"""
    value = os.getenv(varname)
    if not value:
        raise SystemExit(f"{varname} is not set")
    return value


def log_retry_info(retry_state):
    """Meant to be used with tenacity's before_sleep callback"""
    logger.warning(
        f"Retry attempt {retry_state.attempt_number} failed with exception: {retry_state.outcome.exception()}",
    )


def set_expire_time(expire_in_seconds: int) -> str:
    """
    Sets the expiration time based on the current UTC time and the given number of seconds.

    Args:
        expire_in_seconds (int): The number of seconds from now when the expiration should occur.

    Returns:
        str: The expiration time in ISO 8601 format with 'Z' as the UTC indicator.
    """
    return (
        (datetime.now(timezone.utc) + timedelta(seconds=expire_in_seconds))
        .replace(tzinfo=timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def verify_hotkey_in_metagraph(metagraph: bt.metagraph, hotkey: str) -> bool:
    """
    returns true if input hotkey is in input metagraph, false otherwise.
    """
    return hotkey in metagraph.hotkeys


def verify_signature(hotkey: str, signature: str, message: str) -> bool:
    """
    returns true if input signature was created by input hotkey for input message.
    """
    keypair = bt.Keypair(ss58_address=hotkey, ss58_format=42)
    if not keypair.verify(data=message, signature=signature):
        logger.error(f"Invalid signature for address={hotkey}")
        return False

    logger.success(f"Signature verified, signed by {hotkey}")
    return True


def check_stake(subtensor: bt.subtensor, hotkey: str) -> bool:
    """
    returns true if hotkey has enough stake to be a validator and false otherwise.
    """
    from dojo import VALIDATOR_MIN_STAKE

    stake = get_effective_stake(hotkey, subtensor)

    if stake < VALIDATOR_MIN_STAKE:
        return False
    return True
