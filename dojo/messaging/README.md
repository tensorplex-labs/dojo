# messaging layer

- server (e.g. miner)
  - must call serve_synapse with both `async def handler(fastapi.Request, pydantic.BaseModel)`
