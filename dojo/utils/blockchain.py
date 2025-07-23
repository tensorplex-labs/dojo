import bittensor as bt
from loguru import logger

from dojo.objects import ObjectManager
from dojo.utils.netip import get_int_ip_address

from kami import AxonInfo, ServeAxonPayload, SubnetMetagraph

ROOT_WEIGHT = 0.18
ROOT_NETUID = 0


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
    from dojo.constants import ValidatorConstant

    stake = get_effective_stake(hotkey, subtensor)

    if stake < ValidatorConstant.VALIDATOR_MIN_STAKE:
        return False
    return True


async def check_if_axon_served(
    hotkey: str,
    uid: int,
    current_axons: AxonInfo,
    axon_payload: ServeAxonPayload,
    netuid: int,
) -> bool:
    """
    Check if the axon is served successfully.
    """
    current_axon: AxonInfo = current_axons[uid]
    current_axon_ip: str = current_axon.ip
    current_axon_port = current_axon.port

    if not current_axon_ip:
        logger.info(f"Axon not served for hotkey {hotkey} on netuid {netuid}")
        return False

    if (
        await get_int_ip_address(current_axon_ip) == axon_payload.ip
        and axon_payload.port == current_axon_port
    ):
        return True
    return False
