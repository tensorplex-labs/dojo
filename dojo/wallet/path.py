import json
import os
from pathlib import Path

from loguru import logger

from dojo.wallet.types import WalletInfo


def get_wallet_info(
    bittensor_dir: str, wallet_coldkey: str, wallet_hotkey: str
) -> WalletInfo:
    base_dir = os.path.expandvars(bittensor_dir)
    base_dir = Path(base_dir)

    coldkey_path = base_dir / "wallets" / wallet_coldkey / "coldkeypub.txt"
    hotkey_path = base_dir / "wallets" / wallet_coldkey / "hotkeys" / wallet_hotkey

    ss58_coldkey, ss58_hotkey = "", ""
    try:
        with coldkey_path.open("r") as f:
            data = json.loads(f.read())
            ss58_coldkey = data.get("ss58Address")
    except json.JSONDecodeError:
        logger.error(f"Failed to parse coldkey pub file at: {coldkey_path} as JSON")

    try:
        with hotkey_path.open("r") as f:
            data = json.loads(f.read())
            ss58_hotkey = data.get("ss58Address")
    except json.JSONDecodeError:
        logger.error(f"Failed to parse hotkey pub file at: {hotkey_path} as JSON")

    return WalletInfo(
        coldkey=ss58_coldkey,
        hotkey=ss58_hotkey,
        coldkey_path=coldkey_path,
        hotkey_path=hotkey_path,
    )
