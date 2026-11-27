"""Container entry point. Inputs are mounted read-only at /input."""
import base64
import json
import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

from table import read_table


def run():
    inputs = Path("/input")
    job = json.loads((inputs / "job.json").read_bytes())
    with (inputs / "data").open("rb") as stream:
        df = read_table(stream, job["ext"], job["sheet"])
    scope = {"df": df, "pd": pd, "np": np, "plt": plt, "sns": sns}
    exec(compile(job["code"], "<analysis>", "exec"), scope)
    if "result" not in scope:
        raise ValueError("The generated code did not assign result")
    result = scope["result"]
    if isinstance(result, (pd.DataFrame, pd.Series)):
        kind = "table" if isinstance(result, pd.DataFrame) else "series"
        value = json.loads(result.to_json(orient="split", date_format="iso"))
    elif pd.api.types.is_scalar(result):
        kind = "scalar"
        value = json.loads(pd.Series([result]).to_json(orient="values", date_format="iso"))[0]
    else:
        raise ValueError("Expected a DataFrame, Series, or scalar result")

    answer = {"result_type": kind, "result": value}
    plot = Path("plot.png")
    if plot.is_file():
        with plot.open("rb") as stream:
            raw = stream.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024 or not raw.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("Expected a PNG chart under 2 MiB")
        answer["plot_png_base64"] = base64.b64encode(raw).decode("ascii")
    return answer


if __name__ == "__main__":
    # Keep prints from generated code out of the JSON response stream.
    with os.fdopen(os.dup(1), "w", encoding="utf-8") as output:
        os.dup2(2, 1)
        try:
            answer = run()
        except Exception as exc:
            answer = {"error": f"{type(exc).__name__}: {str(exc)[:500]}"}
        json.dump(answer, output, allow_nan=False)
