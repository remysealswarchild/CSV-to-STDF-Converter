"""Parses the Selene CSV layout into structured records."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence
import csv


@dataclass
class TestDefinition:
    column_index: int
    name: str
    test_number: int
    unit: str | None
    lower_limit: float | None
    upper_limit: float | None


@dataclass
class DeviceRecord:
    metadata: Dict[str, str]
    measurements: Dict[int, str]


@dataclass
class ParsedCsv:
    headers: Sequence[str]
    metadata_fields: Sequence[str]
    tests: Sequence[TestDefinition]
    devices: Sequence[DeviceRecord]


def parse_csv(input_path: str) -> ParsedCsv:
    """Return structured data extracted from the bespoke CSV format."""

    rows: List[List[str]] = []
    with Path(input_path).open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.reader(handle)
        for row in reader:
            rows.append([cell.strip() for cell in row])
    if len(rows) < 6:
        raise ValueError("CSV file does not contain enough rows for headers and data")

    header = rows[0]
    test_number_row = rows[1]
    lower_limit_row = rows[2]
    upper_limit_row = rows[3]
    units_row = rows[4]
    data_rows = rows[5:]

    metadata_columns: List[int] = []
    test_definitions: List[TestDefinition] = []

    for idx, title in enumerate(header):
        raw_test_number = _cell(test_number_row, idx)
        test_number = _parse_int(raw_test_number)
        if test_number is None:
            metadata_columns.append(idx)
            continue
        test_definitions.append(
            TestDefinition(
                column_index=idx,
                name=title or f"TEST_{test_number}",
                test_number=test_number,
                unit=_clean_string(_cell(units_row, idx)) or None,
                lower_limit=_parse_float(_cell(lower_limit_row, idx)),
                upper_limit=_parse_float(_cell(upper_limit_row, idx)),
            )
        )

    devices: List[DeviceRecord] = []
    for row in data_rows:
        if not any(cell.strip() for cell in row):
            continue
        metadata = {
            header[idx]: _cell(row, idx)
            for idx in metadata_columns
            if idx < len(header) and header[idx]
        }
        measurements = {
            definition.test_number: _cell(row, definition.column_index)
            for definition in test_definitions
        }
        devices.append(DeviceRecord(metadata=metadata, measurements=measurements))

    return ParsedCsv(
        headers=header,
        metadata_fields=[header[idx] for idx in metadata_columns if header[idx]],
        tests=test_definitions,
        devices=devices,
    )


def _cell(row: Sequence[str], idx: int) -> str:
    if idx >= len(row):
        return ""
    return row[idx].strip()


def _parse_int(value: str | None) -> int | None:
    if not value:
        return None
    value = value.strip()
    if value.lower() in {"na", "nan"}:
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def _parse_float(value: str | None) -> float | None:
    if not value:
        return None
    value = value.strip()
    if value.lower() in {"na", "nan"}:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _clean_string(value: str | None) -> str:
    return (value or "").strip()
