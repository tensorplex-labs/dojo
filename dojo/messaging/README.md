# dojo's messaging layer

## why?
- enables us to use higher compression ratio algorithms like zstandard
- uses aiohttp under the hood for client-side, and fastapi for server side
- uses AsyncRetrying from tenacity, and asyncio.BoundedSemaphore by default for controlling batching & concurrency
- fully typed, so you can simply access your Synapse's fields directly from `response.body`
- dedicated function for batch sending to target URLs


- server (typically miner)
  - must call serve_synapse with both `async def handler(fastapi.Request, pydantic.BaseModel)`
  - must initialise

- client (typically validator)
