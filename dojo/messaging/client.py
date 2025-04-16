import asyncio
from typing import Any

import aiohttp
import substrateinterface
from aiohttp.client import ClientSession
from loguru import logger
from orjson import JSONDecodeError
from pydantic import BaseModel

from dojo.messaging.types import (
    HOTKEY_HEADER,
    MESSAGE_HEADER,
    SIGNATURE_HEADER,
    PydanticModel,
    StdResponse,
)
from dojo.messaging.utils import encode_body
from dojo.protocol import (
    CodeAnswer,
    CompletionResponse,
    TaskSynapseObject,
    TaskTypeEnum,
)


def get_client() -> ClientSession:
    return aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False, limit=256))


def _build_url(url: str, model: BaseModel, protocol: str = "http") -> str:
    if not url.startswith("http") and not url.startswith("https"):
        url = f"{protocol}://{url}"

    return f"{url}/{model.__class__.__name__}"


class Client:
    def __init__(
        self,
        keypair: substrateinterface.Keypair,
        session: ClientSession | None = None,
    ) -> None:
        self._keypair = keypair
        self._session: ClientSession = session or get_client()
        self._compression_headers = {"Content-Encoding": "zstd"}

    def _build_headers(self, keypair: substrateinterface.Keypair) -> dict[str, str]:
        hotkey: str = keypair.ss58_address
        message: str = f"I solemnly swear that I am up to some good. Hotkey: {hotkey}"
        signature: str = "0x" + keypair.sign(message).hex()
        # TODO: use wallet nonce
        return {
            "Content-Type": "application/json",
            SIGNATURE_HEADER: signature,
            HOTKEY_HEADER: hotkey,
            MESSAGE_HEADER: message,
            **self._compression_headers,
        }

    # async def batch_send(
    #     self,
    #     urls: list[str],
    #     models: list[PydanticModel],
    #     semaphore: asyncio.Semaphore | None = None,
    # ) -> list[Response | BaseException]:
    #     """Sends the following payloads to the given URLs concurrently.
    #     Expects that the endpoint is hosted at:
    #         http://<url>/<model_name> where model_name is the name of the Pydantic model
    #
    #     Args:
    #         urls (list[str]): urls
    #         models (list[PydanticModel]): models
    #         keypair (substrateinterface.Keypair): keypair
    #
    #     Returns:
    #         list[Response]: Returns both the aiohttp Response, and the model that
    #             was returned from the server, or the exception if the request failed
    #     """
    #
    #     if semaphore is None:
    #         logger.info("Attempting to batch sending requests without semaphore")
    #         responses = await asyncio.gather(
    #             *[self.send(url, model) for url, model in zip(urls, models)],
    #             return_exceptions=True,
    #         )
    #         for i, response in enumerate(responses):
    #             if isinstance(response, Exception):
    #                 logger.error(f"Error due to exception: {response}")
    #             elif response:
    #                 client_response, model = response
    #                 if client_response.status != http.HTTPStatus.OK:
    #                     logger.error(f"Error due to response: {client_response.status}")
    #
    #     async def _send_with_semaphore(
    #         url: str, model: PydanticModel
    #     ) -> Response:
    #         async with semaphore:
    #             return await self.send(url, model)
    #
    #     responses = await asyncio.gather(
    #         *[_send_with_semaphore(url, model) for url, model in zip(urls, models)],
    #         return_exceptions=True,
    #     )
    #
    #     return responses

    async def send(
        self, url: str, model: PydanticModel
    ) -> tuple[aiohttp.ClientResponse | None, StdResponse[PydanticModel] | None]:
        """Sends the following payload to the given URL.
        Expects that the endpoint is hosted at:
            http://<url>/<model_name> where model_name is the name of the Pydantic model

        Args:
            url (str): url
            model (PydanticModel): model
            keypair (substrateinterface.Keypair): keypair

        Returns:
            Response: Returns both the aiohttp Response, and the model that
                was returned from the server
        """
        compressed = encode_body(model)
        # response: aiohttp.ClientResponse | None = None
        ERROR_RESPONSE = None, None
        async with self._session.post(
            _build_url(url, model),
            data=compressed,
            headers=self._build_headers(self._keypair),
        ) as client_resp:
            logger.info(f"Received response from: {url}, status: {client_resp.status}")
            response_json = {}
            try:
                response_json = await client_resp.json()
            except JSONDecodeError as e:
                logger.error(
                    f"Failed to decode response: {await client_resp.text()}, exception: {e}"
                )
                pass

            if not response_json:
                return ERROR_RESPONSE

            # parse object to the specific model
            logger.info(f"Validator got response from miner: {response_json}")
            try:
                # TODO: fix pyright typing
                error: str | None = response_json.get("error", None)  # pyright: ignore
                metadata: dict[str, Any] = response_json.get("metadata", {})  # pyright: ignore
                body: dict[str, Any] = response_json.get("body", {})  # pyright: ignore

                if body:
                    pydantic_model = model.model_validate(body)
                    return client_resp, StdResponse(
                        body=pydantic_model,
                        error=error,  # pyright: ignore
                        metadata=metadata,  # pyright: ignore
                    )

            except JSONDecodeError as e:
                logger.error(f"Failed to decode response: {e}")

        return ERROR_RESPONSE

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
        # completion_responses=[],
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
    # NOTE: example here to generate a valid signature, message, and hotkey
    keypair = substrateinterface.Keypair.create_from_uri("//Alice")
    message = "bingbong"
    signature = keypair.sign(message)
    logger.info(f"Signature: {signature}")
    logger.info(f"Hotkey: {keypair.ss58_address}")
    logger.info(f"message: {message}")

    # TODO: this should be miner's axon IP
    url = "http://127.0.0.1:8888"
    session = get_client()
    client = Client(session=session, keypair=keypair)
    response, returned_payload = await client.send(url, model=payload_a)

    if response:
        print(f"Status: {response.status}")
        print(f"Response: {await response.text()}")
        print(f"Original size: {len(json_data)} bytes")
        print(f"Compressed size: {len(compressed)} bytes")
        print(f"Compression ratio: {len(compressed) / len(json_data):.2f}")

    if returned_payload:
        print(f"Returned payload: {returned_payload}")
        print(f"{returned_payload.body=}")

    await session.close()


if __name__ == "__main__":
    asyncio.run(main())
