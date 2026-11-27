from typing import BinaryIO

import pandas as pd


def read_table(stream: BinaryIO, ext: str, sheet: str | None) -> pd.DataFrame:
    if ext in (".csv", ".txt"):
        for enc in ("utf-8", "utf-8-sig", "cp1256", "latin-1"):
            try:
                stream.seek(0)
                return pd.read_csv(stream, encoding=enc, sep=None, engine="python")
            except UnicodeDecodeError:
                continue
        raise ValueError("Could not decode CSV with common encodings.")
    if ext in (".xlsx", ".xlsm", ".xls"):
        # sheet_name=None would load all sheets; we load one (first by default)
        return pd.read_excel(stream, sheet_name=sheet if sheet else 0)
    raise ValueError(f"Unsupported file type: {ext} (use .csv or .xlsx)")
