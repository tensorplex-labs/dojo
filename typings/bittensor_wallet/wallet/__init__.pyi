from typing import Any

from substrateinterface import Keypair

class Keyfile:
    def __init__(
        self,
        path: str | None = None,
        name: str | None = None,
        should_save_to_env: bool = False,
    ) -> None: ...
    def __str__(self) -> str: ...
    @property
    def path(self) -> str: ...
    def exists_on_device(self) -> bool: ...
    def is_readable(self) -> bool: ...
    def is_writable(self) -> bool: ...
    def is_encrypted(self) -> bool: ...
    def check_and_update_encryption(
        self, print_result: bool = True, no_prompt: bool = False
    ) -> None: ...
    def encrypt(self, password: str | None = None) -> None: ...
    def decrypt(self, password: str | None = None) -> None: ...
    def env_var_name(self) -> str: ...
    def save_password_to_env(self, password: str | None = None) -> None: ...
    def remove_password_from_env(self) -> None: ...
    @property
    def keypair(self) -> Keypair: ...
    def get_keypair(self, password: str | None = None) -> Keypair: ...
    def set_keypair(
        self,
        keypair: Keypair,
        encrypt: bool = True,
        overwrite: bool = False,
        password: str | None = None,
    ) -> None: ...
    @property
    def data(self): ...
    def make_dirs(self): ...

class Wallet:
    def __init__(
        self,
        name: str | None = None,
        hotkey: str | None = None,
        path: str | None = None,
        config: Any | None = None,
    ) -> None: ...
    def __str__(self) -> str: ...
    @classmethod
    def add_args(cls, parser: Any, prefix: str | None = None) -> Any: ...
    def to_string(self) -> str: ...
    def debug_string(self) -> str: ...
    def create_if_non_existent(
        self,
        coldkey_use_password: bool | None = True,
        hotkey_use_password: bool | None = False,
        save_coldkey_to_env: bool | None = False,
        save_hotkey_to_env: bool | None = False,
        coldkey_password: str | None = None,
        hotkey_password: str | None = None,
        overwrite: bool | None = False,
        suppress: bool | None = False,
    ) -> Wallet: ...
    def create(
        self,
        coldkey_use_password: bool | None = True,
        hotkey_use_password: bool | None = False,
        save_coldkey_to_env: bool | None = False,
        save_hotkey_to_env: bool | None = False,
        coldkey_password: str | None = None,
        hotkey_password: str | None = None,
        overwrite: bool | None = False,
        suppress: bool | None = False,
    ) -> Wallet: ...
    def recreate(
        self,
        coldkey_use_password: bool | None = True,
        hotkey_use_password: bool | None = False,
        save_coldkey_to_env: bool | None = False,
        save_hotkey_to_env: bool | None = False,
        coldkey_password: str | None = None,
        hotkey_password: str | None = None,
        overwrite: bool | None = False,
        suppress: bool | None = False,
    ) -> Wallet: ...
    def get_coldkey(self, password: str | None = None) -> Keypair: ...
    def get_coldkeypub(self, password: str | None = None) -> Keypair: ...
    def get_hotkey(self, password: str | None = None) -> Keypair: ...
    def set_coldkey(
        self,
        keypair: Keypair,
        encrypt: bool = True,
        overwrite: bool = False,
        save_coldkey_to_env: bool = False,
        coldkey_password: str | None = None,
    ) -> None: ...
    def set_coldkeypub(
        self,
        keypair: Keypair,
        encrypt: bool = False,
        overwrite: bool = False,
    ) -> None: ...
    def set_hotkey(
        self,
        keypair: Keypair,
        encrypt: bool = False,
        overwrite: bool = False,
        save_hotkey_to_env: bool = False,
        hotkey_password: str | None = None,
    ) -> None: ...
    @property
    def coldkey(self) -> Keypair: ...
    @property
    def coldkeypub(self) -> Keypair: ...
    @property
    def hotkey(self) -> Keypair: ...
    @property
    def coldkey_file(self) -> Keyfile: ...
    @property
    def coldkeypub_file(self) -> Keyfile: ...
    @property
    def hotkey_file(self) -> Keyfile: ...
    @property
    def name(self) -> str: ...
    @property
    def path(self) -> str: ...
    @property
    def hotkey_str(self) -> str: ...
    def create_coldkey_from_uri(
        self,
        uri: str,
        use_password: bool | None = True,
        overwrite: bool | None = False,
        suppress: bool | None = False,
        save_coldkey_to_env: bool | None = False,
        coldkey_password: str | None = None,
    ) -> None: ...
    def create_hotkey_from_uri(
        self,
        uri: str,
        use_password: bool | None = True,
        overwrite: bool | None = False,
        suppress: bool | None = False,
        save_hotkey_to_env: bool | None = False,
        hotkey_password: str | None = None,
    ) -> None: ...
    def unlock_coldkey(self) -> Keypair: ...
    def unlock_coldkeypub(self) -> Keypair: ...
    def unlock_hotkey(self) -> Keypair: ...
    def new_coldkey(
        self,
        n_words: int | None = 12,
        use_password: bool | None = True,
        overwrite: bool | None = False,
        suppress: bool | None = False,
        save_coldkey_to_env: bool | None = False,
        coldkey_password: str | None = None,
    ) -> Wallet: ...
    def create_new_coldkey(
        self,
        n_words: int | None = 12,
        use_password: bool | None = True,
        overwrite: bool | None = False,
        suppress: bool | None = False,
        save_coldkey_to_env: bool | None = False,
        coldkey_password: str | None = None,
    ) -> Wallet: ...
    def new_hotkey(
        self,
        n_words: int | None = 12,
        use_password: bool | None = True,
        overwrite: bool | None = False,
        suppress: bool | None = False,
        save_hotkey_to_env: bool | None = False,
        hotkey_password: str | None = None,
    ) -> Wallet: ...
    def create_new_hotkey(
        self,
        n_words: int | None = 12,
        use_password: bool | None = True,
        overwrite: bool | None = False,
        suppress: bool | None = False,
        save_coldkey_to_env: bool | None = False,
        coldkey_password: str | None = None,
    ) -> Wallet: ...
    def regenerate_coldkey(
        self,
        mnemonic: str | None = None,
        seed: bytes | None = None,
        json: str | None = None,
        use_password: bool | None = True,
        overwrite: bool | None = False,
        suppress: bool | None = False,
        save_coldkey_to_env: bool | None = False,
        coldkey_password: str | None = None,
    ) -> Wallet: ...
    def regenerate_coldkeypub(
        self,
        ss58_address: str | None = None,
        public_key: bytes | None = None,
        overwrite: bool | None = False,
    ) -> Wallet: ...
    def regenerate_hotkey(
        self,
        mnemonic: str | None = None,
        seed: bytes | None = None,
        json: str | None = None,
        use_password: bool | None = False,
        overwrite: bool | None = False,
        suppress: bool | None = False,
        save_hotkey_to_env: bool | None = False,
        hotkey_password: str | None = None,
    ) -> Wallet: ...
