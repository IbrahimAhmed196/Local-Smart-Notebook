"""Cancellable streaming HTTP for synchronous LLM callers."""
import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import httpx
from app.core.exceptions import GenerationCancelled

POLL_SECONDS = 0.05


class StreamError(RuntimeError):
    """The server returned an invalid or unfinished stream."""


def raise_if_cancelled(cancel_event: Event | None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise GenerationCancelled("LLM generation was cancelled.")


def post_chat_stream(url: str, payload: dict, timeouts: tuple[float, float],
                     cancel_event: Event) -> str:
    raise_if_cancelled(cancel_event)
    # Preserve the synchronous API, including calls from an existing event loop.
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(
            lambda: asyncio.run(_run(url, payload, timeouts, cancel_event))
        ).result()


async def _run(url, payload, timeouts, cancel_event):
    task = asyncio.create_task(_read_stream(url, payload, timeouts))
    try:
        while True:
            raise_if_cancelled(cancel_event)
            done, _ = await asyncio.wait({task}, timeout=POLL_SECONDS)
            raise_if_cancelled(cancel_event)
            if done:
                return task.result()
    finally:
        if not task.done():
            task.cancel()
        # Let the HTTP context managers close the response and connection.
        await asyncio.gather(task, return_exceptions=True)


async def _read_stream(url, payload, timeouts):
    connect, read = timeouts
    timeout = httpx.Timeout(connect=connect, read=read, write=connect, pool=connect)
    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream("POST", url, json=payload) as response:
            response.raise_for_status()
            parts = []
            async for line in response.aiter_lines():
                if not line.strip():
                    continue
                try:
                    packet = json.loads(line)
                    if not isinstance(packet, dict):
                        raise TypeError("packet must be an object")
                    if "error" in packet:
                        raise StreamError(f"Ollama streaming error: {packet['error']}")
                    content = packet.get("message", {}).get("content", "")
                    if not isinstance(content, str) or not isinstance(packet.get("done", False), bool):
                        raise TypeError("invalid stream fields")
                except (ValueError, TypeError, AttributeError) as exc:
                    raise StreamError("Ollama sent an invalid stream packet.") from exc
                parts.append(content)
                if packet.get("done") is True:
                    return "".join(parts)
    raise StreamError("Ollama closed the stream before generation finished.")