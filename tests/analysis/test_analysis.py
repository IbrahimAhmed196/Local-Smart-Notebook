import json
import os
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.analysis import codegen
from app.main import app
from app.sandbox import executor
from app.core.config import settings
from app.llm.ollama_client import LlmChatError, OllamaChatClient, OllamaJSONClient

client = TestClient(app)
prefix = f"{settings.api_prefix}/analysis"
sales = Path(__file__).with_name("sales_test.csv")


def test_schema_uses_selected_sheet():
    workbook = BytesIO()
    with pd.ExcelWriter(workbook, engine="openpyxl") as writer:
        pd.DataFrame({"first": [1]}).to_excel(writer, sheet_name="First", index=False)
        pd.DataFrame({"sales": [23]}).to_excel(writer, sheet_name="Sales", index=False)
    reply = client.post(f"{prefix}/schema", files={"file": ("book.xlsx", workbook.getvalue())},
                        data={"sheet": "Sales"})
    assert reply.status_code == 200
    assert "'sales'" in reply.json()["schema"]
    assert "'first'" not in reply.json()["schema"]


@pytest.mark.parametrize("model", [None, "custom-model"])
def test_analyze_uses_shared_chat(monkeypatch, model):
    monkeypatch.setattr(executor, "execute", Mock(return_value={"result_type": "scalar", "result": 1}))
    calls = []
    code = "result = df.groupby('region')['total'].sum()"

    def chat(self, messages, **options):
        calls.append((self.model_name, messages, options))
        return f"```python\n{code}\n```"

    monkeypatch.setattr(OllamaChatClient, "chat", chat)
    monkeypatch.setattr(settings, "ollama_model", "default-model")
    form = {"question": "Total by region?", "show_prompt": "true"}
    if model:
        form["model"] = model
    reply = client.post(f"{prefix}/analyze", files={"file": (sales.name, sales.read_bytes())}, data=form)
    assert reply.status_code == 200
    body = reply.json()
    assert body["code"] == code and body["syntax_error"] is None
    assert body["model"] == "qwen2.5-coder:7b"
    assert body["rows"] == len(pd.read_csv(sales))
    assert "region" in body["columns"] and form["question"] in body["prompt"]
    assert calls == [(body["model"], [
        {"role": "system", "content": codegen.SYSTEM_PROMPT},
        {"role": "user", "content": body["prompt"]},
    ], {"temperature": 0.1, "num_ctx": 4096})]


def test_analyze_form_has_no_model_field():
    spec = app.openapi()
    content = spec["paths"][f"{prefix}/analyze"]["post"]["requestBody"]["content"]
    ref = content["multipart/form-data"]["schema"]["$ref"]
    schema = spec["components"]["schemas"][ref.rsplit("/", 1)[1]]
    assert "model" not in schema["properties"]


def test_generation_failure_and_syntax_errors(monkeypatch):
    chat = Mock(side_effect=[LlmChatError("offline"), "result = (", "result = [", "result = {"])
    monkeypatch.setattr(OllamaChatClient, "chat", chat)
    kwargs = {"files": {"file": (sales.name, sales.read_bytes())}, "data": {"question": "Total?"}}
    assert client.post(f"{prefix}/analyze", **kwargs).status_code == 503
    result = client.post(f"{prefix}/analyze", **kwargs).json()
    assert result["detail"].startswith("SyntaxError")
    assert result["code"] == "result = {"
    assert chat.call_count == 4
    assert "result = [" in chat.call_args.args[0][1]["content"]
    assert "prompt" not in result


def test_invalid_upload_and_question():
    files = {"file": ("table.pdf", b"data")}
    assert client.post(f"{prefix}/schema", files=files).status_code == 400
    assert client.post(f"{prefix}/analyze", files=files, data={"question": " "}).status_code == 400

def test_analyze_rejects_invalid_generated_code(monkeypatch):
    monkeypatch.setattr(OllamaChatClient, "chat", Mock(return_value="result = ("))
    reply = client.post(f"{prefix}/analyze", files={"file": (sales.name, sales.read_bytes())},
                        data={"question": "Total?"})
    assert reply.status_code == 422
    assert "SyntaxError" in reply.json()["detail"]


def test_analyze_passes_original_upload_and_generated_code(monkeypatch):
    code = "result = len(df)"
    monkeypatch.setattr(OllamaChatClient, "chat", Mock(return_value=code))

    def run(directory):
        assert (directory / "data").read_bytes() == sales.read_bytes()
        assert json.loads((directory / "job.json").read_bytes()) == {
            "code": code, "ext": ".csv", "sheet": None,
        }
        return {"result_type": "scalar", "result": 120}

    monkeypatch.setattr(executor, "_run_container", run)
    reply = client.post(f"{prefix}/analyze", files={"file": (sales.name, sales.read_bytes())},
                        data={"question": "How many rows?"})
    assert reply.status_code == 200
    assert reply.json()["code"] == code
    assert reply.json()["result"] == reply.json()["rows"] == 120


requires_docker = pytest.mark.skipif(
    os.getenv("RUN_ANALYSIS_DOCKER_TESTS") != "1", reason="requires built Docker image"
)


@requires_docker
@pytest.mark.parametrize("code, status", [
    ("result = df.groupby('region')['total'].sum(); result.plot.bar(); plt.savefig('plot.png')", 200),
    ("result = df['total'].sum()", 200),
    ("result = df[['total']].head(2)", 200),
    ("result = df['missing_column']", 422),
])
def test_analyze_in_docker(monkeypatch, code, status):
    monkeypatch.setattr(OllamaChatClient, "chat", Mock(return_value=code))
    reply = client.post(f"{prefix}/analyze", files={"file": (sales.name, sales.read_bytes())},
                        data={"question": "Analyze sales"})
    assert reply.status_code == status, reply.text[:500]
    body = reply.json()
    assert body["code"] == code
    df = pd.read_csv(sales)
    if status == 422:
        assert "KeyError" in body["detail"]
    elif body["result_type"] == "series":
        result = body["result"]
        assert dict(zip(result["index"], result["data"])) == pytest.approx(df.groupby("region")["total"].sum().to_dict())
        assert body["plot_png_base64"].startswith("iVBOR")
    elif body["result_type"] == "table":
        assert body["result"]["columns"] == ["total"]
        assert body["result"]["data"] == df[["total"]].head(2).values.tolist()
    else:
        assert body["result"] == pytest.approx(df["total"].sum())


@requires_docker
def test_month_end_revenue_chart(monkeypatch):
    code = """df['order_date'] = pd.to_datetime(df['order_date'])
df.set_index('order_date', inplace=True)
result = df.resample('M')['total'].sum()
result.plot(kind='line')
plt.savefig('plot.png', bbox_inches='tight')"""
    chat = Mock(side_effect=[code, code.replace("resample('M')", "resample('ME')")])
    monkeypatch.setattr(OllamaChatClient, "chat", chat)
    reply = client.post(f"{prefix}/analyze", files={"file": (sales.name, sales.read_bytes())},
                        data={"question": "Plot monthly revenue"})
    assert reply.status_code == 200, reply.text[:500]
    body = reply.json()
    repair = chat.call_args.args[0][1]["content"]
    assert code in repair and "Invalid frequency" in repair and "Plot monthly revenue" in repair
    df = pd.read_csv(sales)
    expected = df.groupby(df["order_date"].str[:7])["total"].sum()
    result = body["result"]
    assert dict(zip([date[:7] for date in result["index"]], result["data"])) == pytest.approx(expected.to_dict())
    assert body["plot_png_base64"].startswith("iVBOR")
    assert "resample('ME')" in body["code"]


@requires_docker
def test_execution_deadline(monkeypatch):
    monkeypatch.setattr(executor, "TIMEOUT_SECONDS", 2)
    monkeypatch.setattr(OllamaChatClient, "chat", Mock(return_value="while True: pass"))
    reply = client.post(f"{prefix}/analyze", files={"file": (sales.name, sales.read_bytes())},
                        data={"question": "Analyze sales"})
    assert reply.status_code == 504, reply.text
