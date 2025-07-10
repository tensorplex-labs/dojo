from redis_om import Field, HashModel


# NOTE: minimal way of saving data for miners, to keep things flexible
class ServedRequest(HashModel):
    """Represents a served request for the miner, for requests that came from a validator"""

    validator_task_id: str = Field(index=True)
    hotkey: str = Field(index=True)
    dojo_task_id: str = Field(index=True)
