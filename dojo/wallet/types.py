from pathlib import Path

from pydantic import BaseModel


class WalletInfo(BaseModel):
    coldkey: str
    hotkey: str
    coldkey_path: Path
    hotkey_path: Path
