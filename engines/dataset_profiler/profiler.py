"""
Deterministic dataset profiler engine built on Pandas.
Extracts schema, column data types, row/column cardinality, null distributions,
and duplicate record counts across CSV, XLSX, and JSON datasets.
"""

import io
import json
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional
import pandas as pd


class ProfilingError(Exception):
    """Raised when dataset profiling fails due to malformed content."""
    pass


@dataclass(frozen=True)
class ProfilingResult:
    """Immutable structured summary of deterministic dataset profiling."""
    row_count: int
    column_count: int
    columns: List[str]
    column_types: Dict[str, str]
    null_counts: Dict[str, int]
    null_percentages: Dict[str, float]
    duplicate_row_count: int
    file_format: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class DatasetProfiler:
    """
    Deterministic data inspection engine.
    Parses and profiles tabular data in memory without executing embedded code.
    """

    @staticmethod
    def _map_dtype(dtype: Any) -> str:
        """Map Pandas internal dtypes to clean, normalized semantic categories."""
        dtype_str = str(dtype).lower()
        if "int" in dtype_str:
            return "integer"
        elif "float" in dtype_str:
            return "float"
        elif "bool" in dtype_str:
            return "boolean"
        elif "datetime" in dtype_str:
            return "datetime"
        elif "category" in dtype_str:
            return "categorical"
        return "string"

    @classmethod
    def load_dataframe(cls, content: bytes, file_format: str) -> pd.DataFrame:
        """
        Safely load bytes into a Pandas DataFrame based on normalized format.
        """
        fmt = file_format.lower().lstrip(".")
        buffer = io.BytesIO(content)

        try:
            if fmt == "csv":
                # Parse CSV with safe engine
                try:
                    df = pd.read_csv(buffer, low_memory=False, encoding="utf-8")
                except UnicodeDecodeError:
                    buffer.seek(0)
                    df = pd.read_csv(buffer, low_memory=False, encoding="latin-1")
            elif fmt == "xlsx":
                # Parse Excel using openpyxl engine
                df = pd.read_excel(buffer, engine="openpyxl")
            elif fmt == "json":
                # Parse JSON array or records
                try:
                    # Attempt standard JSON read
                    df = pd.read_json(buffer)
                except Exception:
                    # Fallback for nested JSON structure or records list
                    buffer.seek(0)
                    raw_data = json.loads(content.decode("utf-8"))
                    if isinstance(raw_data, list):
                        df = pd.DataFrame(raw_data)
                    elif isinstance(raw_data, dict):
                        # Try records key or single record
                        if "data" in raw_data and isinstance(raw_data["data"], list):
                            df = pd.DataFrame(raw_data["data"])
                        elif "records" in raw_data and isinstance(raw_data["records"], list):
                            df = pd.DataFrame(raw_data["records"])
                        else:
                            df = pd.json_normalize(raw_data)
                    else:
                        raise ValueError("JSON data is not in an iterable tabular structure")
            else:
                raise ProfilingError(f"Unsupported dataset format: {file_format}")
        except Exception as exc:
            raise ProfilingError(f"Failed to parse {file_format.upper()} dataset: {str(exc)}") from exc

        # Ensure dataframe is not completely empty
        if df.empty or len(df.columns) == 0:
            raise ProfilingError("Dataset contains no data or no columns (empty dataset)")

        return df

    @classmethod
    def profile(cls, content: bytes, file_format: str) -> ProfilingResult:
        """
        Deterministically profile dataset bytes.

        Calculates:
        - Total row count
        - Total column count
        - Column list
        - Inferred normalized column types
        - Null counts per column
        - Null percentages per column (rounded to 2 decimal places)
        - Duplicate row count
        """
        df = cls.load_dataframe(content, file_format)

        row_count = int(len(df))
        column_count = int(len(df.columns))
        columns = [str(col) for col in df.columns]

        column_types: Dict[str, str] = {}
        null_counts: Dict[str, int] = {}
        null_percentages: Dict[str, float] = {}

        for col in df.columns:
            col_str = str(col)
            series = df[col]
            column_types[col_str] = cls._map_dtype(series.dtype)
            n_null = int(series.isna().sum())
            null_counts[col_str] = n_null
            pct = round((n_null / row_count) * 100, 2) if row_count > 0 else 0.0
            null_percentages[col_str] = pct

        duplicate_count = int(df.duplicated().sum())

        return ProfilingResult(
            row_count=row_count,
            column_count=column_count,
            columns=columns,
            column_types=column_types,
            null_counts=null_counts,
            null_percentages=null_percentages,
            duplicate_row_count=duplicate_count,
            file_format=file_format.lower().lstrip("."),
        )
