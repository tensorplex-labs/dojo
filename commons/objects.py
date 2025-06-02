from loguru import logger

from dojo.utils import get_config


class ObjectManager:
    _miner = None
    _validator = None
    _seed_dataset_iter = None
    _config = None

    @classmethod
    async def get_miner(cls):
        from neurons.miner import Miner

        if cls._miner is None:
            try:
                cls._miner = await Miner()
            except Exception as e:
                logger.error(f"Failed to initialize Miner: {e}")
                raise
        return cls._miner

    @classmethod
    async def get_validator(cls):
        from neurons.validator import Validator

        if cls._validator is None:
            try:
                cls._validator = await Validator()
            except Exception as e:
                logger.error(f"Failed to initialize Validator: {e}")
                raise
        return cls._validator

    @classmethod
    def get_config(cls):
        if cls._config is None:
            cls._config = get_config()
        return cls._config
