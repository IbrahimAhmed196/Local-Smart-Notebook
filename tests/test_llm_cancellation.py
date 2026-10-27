"""LLM-03: cancellation, stream cleanup, and JSON retry compatibility."""
import asyncio
import json
import time
from threading import Event, Thread
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import Mock
import httpx
import pytest
from pydantic import BaseModel
from app.core.exceptions import GenerationCancelled
from app.llm import cancellation as transport
from app.llm.ollama_client import (
    OllamaJSONClient,
    OllamaError as LlmError,
    OllamaTimeoutError as LlmTimeoutError,
)
from tests.fake_llm import ScriptedLLMClient


class Answer(BaseModel):
    title: str


class Stream(httpx.AsyncByteStream):
    def __init__(self, packets, started=None):
        self.packets, self.started, self.closed = packets, started, False

    async def __aiter__(self):
        for packet in self.packets:
            yield (json.dumps(packet) + "\n").encode()
        if self.started is not None:
            self.started.set()
            await asyncio.sleep(5)

    async def aclose(self):
        self.closed = True


@pytest.fixture
def mock_http(monkeypatch):
    real_client, calls = httpx.AsyncClient, []

    def install(handler):
        async def record(request):
            calls.append(json.loads(request.content))
            return await handler(request)

        monkeypatch.setattr(
            transport.httpx, "AsyncClient",
            lambda **kw: real_client(transport=httpx.MockTransport(record), **kw),
        )
        return calls

    return install


def reply(content='{"title":"Hello"}'):
    return {"message": {"content": content}, "done": True}


@pytest.mark.parametrize("before_headers", [False, True])
def test_cancel_silent_connection(mock_http, before_headers):
    started, cancel, header_cancelled = Event(), Event(), Event()
    stream = Stream([{"message": {"content": "partial"}}], started)

    async def handler(request):
        if before_headers:
            started.set()
            try:
                await asyncio.sleep(5)
            finally:
                header_cancelled.set()
        return httpx.Response(200, stream=stream)

    calls = mock_http(handler)

    def stop():
        if started.wait(3):
            time.sleep(0.1)
        cancel.set()

    worker = Thread(target=stop)
    worker.start()
    begin = time.monotonic()
    try:
        with pytest.raises(GenerationCancelled):
            OllamaJSONClient().generate_json("p", Answer, cancel_event=cancel)
    finally:
        cancel.set()
        worker.join()

    assert started.is_set() and time.monotonic() - begin < 2
    assert len(calls) == 1 and calls[0]["stream"] is True
    assert header_cancelled.is_set() if before_headers else stream.closed


def test_streaming_keeps_schema_fallback_and_retry(mock_http):
    streams = [
        Stream([reply("{}")]),
        Stream([{"message": {"content": '{"title":'}}, reply('"Hello"}')]),
    ]
    responses = iter(streams)

    async def handler(request):
        if isinstance(json.loads(request.content)["format"], dict):
            return httpx.Response(400)
        return httpx.Response(200, stream=next(responses))

    calls = mock_http(handler)
    client = OllamaJSONClient(structured_output=True)
    assert client.generate_json("p", Answer, cancel_event=Event()).title == "Hello"
    assert [isinstance(c["format"], dict) for c in calls] == [True, False, False]
    assert "previous answer was rejected" in calls[2]["messages"][1]["content"]
    assert (client.calls, client.bad_answers) == (1, 1)
    assert all(stream.closed for stream in streams)


@pytest.mark.parametrize("status", [400, 404, 500])
def test_stream_http_errors_do_not_loop(mock_http, status):
    async def handler(request):
        return httpx.Response(status)

    calls = mock_http(handler)
    with pytest.raises(LlmError):
        OllamaJSONClient(structured_output=False).generate_json(
            "p", Answer, cancel_event=Event()
        )
    assert len(calls) == 1


def test_pre_cancel_makes_no_request(monkeypatch):
    event = Event()
    event.set()
    client, post = OllamaJSONClient(), Mock()
    monkeypatch.setattr(client, "_post_cancellable", post)

    with pytest.raises(GenerationCancelled):
        client.generate_json("p", Answer, cancel_event=event)
    post.assert_not_called()


def test_fake_preserves_response_when_cancelled():
    fake = ScriptedLLMClient({"title": "ok"})
    event = Event()
    event.set()

    with pytest.raises(GenerationCancelled):
        fake.generate_json("p", Answer, cancel_event=event)
    assert fake.remaining == 1 and fake.calls == []

    event.clear()
    assert fake.generate_json("p", Answer, cancel_event=event).title == "ok"
    fake.assert_finished()


@pytest.mark.parametrize("packets,message", [
    ([{"message": {"content": '{"title":"partial"}'}}], "before generation finished"),
    ([{"error": "model stopped"}], "model stopped"),
])
def test_broken_stream_is_not_success(mock_http, packets, message):
    stream = Stream(packets)

    async def handler(request):
        return httpx.Response(200, stream=stream)

    calls = mock_http(handler)
    with pytest.raises(LlmError, match=message):
        OllamaJSONClient().generate_json("p", Answer, cancel_event=Event())
    assert stream.closed and len(calls) == 1


def test_stream_timeout_is_not_retried(mock_http):
    async def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    calls = mock_http(handler)
    with pytest.raises(LlmTimeoutError):
        OllamaJSONClient().generate_json("p", Answer, cancel_event=Event())
    assert len(calls) == 1


def test_slide_writer_propagates_control_errors():
    from app.agents.slide_content_agent import generate_slide_content
    from app.schemas.slides import SlideOutlineItem

    fake = ScriptedLLMClient(GenerationCancelled("stop"))
    item = SlideOutlineItem(
        slide_number=1, title="Title", purpose="Introduce", layout_type="title"
    )
    with pytest.raises(GenerationCancelled):
        generate_slide_content(
            item, presentation_title="Title", audience="Team", client=fake
        )
    fake.assert_finished()


def test_real_http_stream_is_closed_on_cancel(monkeypatch):
    # Localhost tests must not inherit an outbound proxy.
    for name in (
        "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
        "http_proxy", "https_proxy", "all_proxy",
    ):
        monkeypatch.delenv(name, raising=False)

    started, disconnected, cancel = Event(), Event(), Event()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.end_headers()
            self.wfile.write(b'{"message":{"content":"partial"},"done":false}\n')
            self.wfile.flush()
            started.set()
            self.connection.settimeout(3)
            try:
                if self.connection.recv(1) == b"":
                    disconnected.set()
            except OSError:
                pass
            self.close_connection = True

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    outcomes = []

    def run():
        try:
            OllamaJSONClient(
                base_url=f"http://127.0.0.1:{server.server_port}", read_timeout=5
            ).generate_json("Hi", Answer, cancel_event=cancel)
        except Exception as exc:
            outcomes.append(exc)

    worker = Thread(target=run, daemon=True)
    worker.start()
    try:
        assert started.wait(3), repr(outcomes)
        begin = time.monotonic()
        cancel.set()
        worker.join(2)
        assert not worker.is_alive() and time.monotonic() - begin < 2
        assert len(outcomes) == 1 and isinstance(outcomes[0], GenerationCancelled)
        assert disconnected.wait(1)
    finally:
        cancel.set()
        server.shutdown()
        server.server_close()
        thread.join(2)
        worker.join(6)