import asyncio

import aiohttp
from aiohttp.client import ClientSession
from loguru import logger
from orjson import JSONDecodeError
from pydantic import BaseModel

from dojo.messaging.types import PydanticModel
from dojo.messaging.utils import encode_body
from dojo.protocol import (
    CodeAnswer,
    CompletionResponse,
    TaskSynapseObject,
    TaskTypeEnum,
)


def get_client() -> ClientSession:
    return aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False, limit=256))


def _build_url(url: str, model: BaseModel, protocol: str = "http"):
    if not url.startswith("http") and not url.startswith("https"):
        url = f"{protocol}://{url}"

    return f"{url}/{model.__class__.__name__}"


class Client:
    def __init__(self, session: ClientSession | None = None) -> None:
        self._session: ClientSession = session or get_client()
        self._headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Content-Encoding": "zstd",
        }
        self._compression_headers = {"Content-Encoding": "zstd"}

    def _build_headers(self) -> dict[str, str]:
        return {"Content-Type": "application/json", **self._compression_headers}

    async def send(
        self, url: str, model: PydanticModel
    ) -> tuple[aiohttp.ClientResponse | None, PydanticModel | None]:
        """Sends the following payload to the given URL.
        Expects that the endpoint is hosted at:
            http://<url>/<model_name> where model_name is the name of the Pydantic model

        Args:
            url (str): url
            model (PydanticModel): model

        Returns:
            tuple[aiohttp.ClientResponse | None, PydanticModel | None]: Returns
                both the aiohttp Response, and the model that was returned from
                the server
        """
        compressed = encode_body(model)
        async with self._session.post(
            _build_url(url, model), data=compressed, headers=self._build_headers()
        ) as response:
            response = await response.json()
            # parse object to the specific model
            logger.info(f"Validator got response from miner: {response}")
            try:
                pydantic_model = model.model_validate(response)
                return response, pydantic_model
            except JSONDecodeError as e:
                logger.error(f"Failed to decode response: {e}")
        return None, None

    async def cleanup(self):
        try:
            await self._session.close()
        except Exception:
            pass


# NOTE: example usage below
async def main():
    payload_a = TaskSynapseObject(
        prompt="Hello",
        task_type=TaskTypeEnum.CODE_GENERATION,
        completion_responses=[
            CompletionResponse(
                model="gpt-4",
                completion=CodeAnswer(files=[]),
                completion_id="123",
            )
        ],
        expire_at="2026-10-01T00:00:00Z",
    )
    compressed = encode_body(payload_a)
    json_data = payload_a.model_dump_json()

    # TODO: this should be miner's axon IP
    url = "http://127.0.0.1:8888"
    # NOTE: just testing compression ratios here
    # async with aiohttp.ClientSession() as session:
    #     # Test with normal JSON
    #     async with session.post(
    #         "http://localhost:8888/TaskSynapseObject",
    #         data=compressed,
    #         headers={"Content-Type": "application/json", "Content-Encoding": "zstd"},
    #     ) as response:
    #         print(f"Status: {response.status}")
    #         print(f"Response: {await response.text()}")
    #         print(f"Original size: {len(json_data)} bytes")
    #         print(f"Compressed size: {len(compressed)} bytes")
    #         print(f"Compression ratio: {len(compressed) / len(json_data):.2f}")

    session = get_client()
    client = Client(session=session)
    response, returned_payload = await client.send(url, model=payload_a)
    if response:
        print(f"Status: {response.status}")
        print(f"Response: {await response.text()}")
        print(f"Original size: {len(json_data)} bytes")
        print(f"Compressed size: {len(compressed)} bytes")
        print(f"Compression ratio: {len(compressed) / len(json_data):.2f}")
    if returned_payload:
        print(f"Returned payload: {returned_payload}")


if __name__ == "__main__":
    asyncio.run(main())
