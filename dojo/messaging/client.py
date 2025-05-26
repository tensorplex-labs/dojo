import asyncio
import http
from typing import Any, Sequence

import aiohttp
import orjson
import substrateinterface
import zstandard as zstd
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


async def _log_context(
    response: tuple[aiohttp.ClientResponse | None, StdResponse[PydanticModel] | None]
    | BaseException,
) -> None:
    if isinstance(response, BaseException):
        logger.error(f"Error due to exception: {response}")
    else:
        client_response, std_response = response
        if client_response and client_response.status != http.HTTPStatus.OK:
            logger.error(
                f"NOT OK, HTTP status: {client_response.status}, text: {client_response.text()} error: {std_response.error if std_response else ''}, metadata: {std_response.metadata if std_response else ''}"
            )


class Client:
    def __init__(
        self,
        keypair: substrateinterface.Keypair,
        session: ClientSession | None = None,
    ) -> None:
        self._keypair = keypair
        self._session: ClientSession = session or get_client()
        self._compression_headers = {
            "content-encoding": "zstd",
            "accept-encoding": "zstd",
        }

    def _build_headers(self) -> dict[str, str]:
        hotkey: str = self._keypair.ss58_address
        message: str = f"I solemnly swear that I am up to some good. Hotkey: {hotkey}"
        signature: str = "0x" + self._keypair.sign(message).hex()
        # TODO: use wallet nonce
        headers = {
            "content-type": "application/json",
            SIGNATURE_HEADER: signature,
            HOTKEY_HEADER: hotkey,
            MESSAGE_HEADER: message,
            **self._compression_headers,
        }
        logger.debug(f"Sending request with headers: {headers}")
        return headers

    async def batch_send(
        self,
        urls: list[str],
        models: list[PydanticModel],
        semaphore: asyncio.Semaphore | None = None,
        **kwargs: Any,
    ) -> Sequence[
        tuple[aiohttp.ClientResponse | None, StdResponse[PydanticModel] | None]
        | BaseException
    ]:
        """Sends the following payloads to the given URLs concurrently.
        Expects that the endpoint is hosted at:
            http://<url>/<model_name> where model_name is the name of the Pydantic model

        Args:
            urls (list[str]): urls
            models (list[PydanticModel]): models
            keypair (substrateinterface.Keypair): keypair

        Returns:
            list[Response]: Returns both the aiohttp Response, and the model that
                was returned from the server, or the exception if the request failed
        """

        if semaphore is None:
            logger.info("Attempting to batch sending requests without semaphore")
            responses = await asyncio.gather(
                *[self.send(url, model, **kwargs) for url, model in zip(urls, models)],
                return_exceptions=True,
            )
            for r in responses:
                await _log_context(r)

            return responses

        async def _send_with_semaphore(
            url: str, model: PydanticModel
        ) -> tuple[aiohttp.ClientResponse | None, StdResponse[PydanticModel] | None]:
            async with semaphore:
                return await self.send(url, model, **kwargs)

        responses = await asyncio.gather(
            *[_send_with_semaphore(url, model) for url, model in zip(urls, models)],
            return_exceptions=True,
        )
        for r in responses:
            await _log_context(r)

        return responses

    async def send(
        self, url: str, model: PydanticModel, timeout_sec: int = 10, **kwargs: Any
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
        _headers = self._build_headers()
        payload = encode_body(model, _headers)
        # response: aiohttp.ClientResponse | None = None
        ERROR_RESPONSE = None, None
        async with self._session.post(
            _build_url(url, model),
            data=payload,
            headers=_headers,
            timeout=aiohttp.ClientTimeout(total=timeout_sec),
        ) as client_resp:
            logger.info(f"Received response from: {url}, status: {client_resp.status}")
            response_json = {}
            try:
                if client_resp.headers.get("content-encoding", "").lower() == "zstd":
                    logger.info("Attempting zstd decoding")
                    response_bytes = await client_resp.read()
                    dctx = zstd.ZstdDecompressor()
                    decompressed_bytes = dctx.decompress(response_bytes)
                    response_text = decompressed_bytes.decode()
                    response_json = orjson.loads(response_text)
                    logger.success(
                        f"Response JSON: {response_json}, type: {type(response_json)}"
                    )
                else:
                    response_json = await client_resp.json()
            except JSONDecodeError as e:
                logger.error(
                    f"Failed to decode response: {await client_resp.text()}, exception: {e}"
                )

            if not response_json:
                logger.error("Empty response JSON received")
                return ERROR_RESPONSE

            try:
                # TODO: fix pyright typing
                error: str | None = response_json.get("error", None)  # pyright: ignore
                metadata: dict[str, Any] = response_json.get("metadata", {})  # pyright: ignore
                body: dict[str, Any] = response_json.get("body", {})  # pyright: ignore

                if body:
                    try:
                        # parse object to the specific model
                        pydantic_model = model.model_validate(body)
                        return client_resp, StdResponse(
                            body=pydantic_model,
                            error=error,  # pyright: ignore
                            metadata=metadata,  # pyright: ignore
                        )
                    except Exception as e:
                        logger.error(
                            f"Failed to validate model with body: {e}, returning the raw body"
                        )
                        # Return the raw body if validation fails
                        return client_resp, StdResponse(
                            body=model.model_construct(**body),
                            error=error,  # pyright: ignore
                            metadata=metadata,  # pyright: ignore
                        )
                else:
                    logger.warning("Response body is empty, returning empty model")
                    return client_resp, StdResponse(
                        body=model.model_construct(),
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

    async def health_check(self, url: str, timeout_sec: int = 10) -> bool:
        """
        Simple health check to verify if a server is up and running.

        Args:
            url (str): Base URL of the server (without /health)
            timeout_sec (int): Timeout in seconds

        Returns:
            bool: True if server is healthy, False otherwise
        """
        if not url.startswith("http") and not url.startswith("https"):
            url = f"http://{url}"

        health_url = f"{url}/health"

        try:
            async with self._session.get(
                health_url,
                timeout=aiohttp.ClientTimeout(total=timeout_sec),
            ) as response:
                logger.info(f"Health check to {health_url}: status={response.status}")
                return response.status == http.HTTPStatus.OK
        except Exception as e:
            logger.error(f"Health check failed for {health_url}: {str(e)}")
            return False


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
    is_healthy = await client.health_check(url)
    logger.info(f"Server health check: {is_healthy}")
    response, returned_payload = await client.send(url, model=payload_a)
    compressed = encode_body(payload_a, client._build_headers())  # pyright: ignore

    if response:
        logger.debug(f"Status: {response.status}")
        logger.debug(f"Original size: {len(json_data)} bytes")
        logger.debug(f"Compressed size: {len(compressed)} bytes")
        logger.debug(f"Compression ratio: {len(compressed) / len(json_data):.2f}")

    if returned_payload:
        logger.debug(f"Returned payload: {returned_payload}")
        logger.debug(f"{returned_payload.body=}")

    try:
        await client.cleanup()
        await session.close()
    except Exception:
        logger.warning("Exception occurred while cleaning up the client session")
        pass


if __name__ == "__main__":
    asyncio.run(main())
