# (c) Copyright Derrick Tunde.
# git repo https://github.com/remysealswarchild/
# All other rights reserved.
"""CLI utility that converts the provided CSV file into an STDF v4 stream."""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from stdf_converter.csv_parser import ParsedCsv, TestDefinition, parse_csv
from stdf_converter import writer as stdf_writer


@dataclass
class MetaConfig:
    mir_overrides: Dict[str, str]
    atr_entries: List[str]
    head_number: int
    site_number: int


@dataclass
class ConversionJob:
    input_path: Path
    output_path: Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="input.csv", help="Path to the CSV input file")
    parser.add_argument("--output", default="out.stdf", help="Path to the STDF output file")
    parser.add_argument(
        "--inputs",
        nargs="+",
        help="Optional list of CSV files to batch convert (overrides --input/--output)",
    )
    parser.add_argument(
        "--output-dir",
        default=".",
        help="Destination directory for generated STDF files when using --inputs",
    )
    parser.add_argument("--meta", help="Optional JSON file with MIR overrides and ATR notes")
    parser.add_argument("--head", type=int, default=1, help="Default test head number")
    parser.add_argument("--site", type=int, default=1, help="Default site number")
    args = parser.parse_args()

    jobs = build_jobs(args)
    if not jobs:
        raise SystemExit("No input files were supplied")

    meta_cfg = load_meta_config(args.meta, default_head=args.head, default_site=args.site)
    failures: List[tuple[ConversionJob, Exception]] = []
    for job in jobs:
        try:
            convert_csv_file(job.input_path, job.output_path, meta_cfg, source_label="CLI")
            print(f"[OK] {job.input_path} → {job.output_path}")
        except Exception as exc:  # noqa: BLE001
            failures.append((job, exc))
            print(f"[FAIL] {job.input_path}: {exc}", file=sys.stderr)

    if failures:
        print(f"Completed with {len(failures)} error(s).", file=sys.stderr)
        for job, exc in failures:
            print(f"  - {job.input_path} failed: {exc}", file=sys.stderr)
        raise SystemExit(1)


def load_meta_config(meta_path: str | None, default_head: int, default_site: int) -> MetaConfig:
    if not meta_path:
        return MetaConfig(mir_overrides={}, atr_entries=[], head_number=default_head, site_number=default_site)
    raw: Dict[str, object]
    with Path(meta_path).open() as handle:
        raw = json.load(handle)
        if not isinstance(raw, dict):
            raise ValueError("Metadata JSON must be an object")
    mir_overrides_raw = raw.get("mir_overrides", {})
    if not isinstance(mir_overrides_raw, dict):
        mir_overrides_raw = {}
    atr_entries_raw = raw.get("atr_entries", [])
    if not isinstance(atr_entries_raw, list):
        atr_entries_raw = []
    return MetaConfig(
        mir_overrides={k: str(v) for k, v in mir_overrides_raw.items()},
        atr_entries=[str(item) for item in atr_entries_raw],
        head_number=int(raw.get("head_number", default_head)),
        site_number=int(raw.get("site_number", default_site)),
    )


def build_jobs(args) -> List[ConversionJob]:
    if args.inputs:
        output_dir = Path(args.output_dir or ".").expanduser()
        output_dir.mkdir(parents=True, exist_ok=True)
        return [
            ConversionJob(Path(input_path), output_dir / (Path(input_path).stem + ".stdf"))
            for input_path in args.inputs
        ]

    single_output = Path(args.output).expanduser()
    single_output.parent.mkdir(parents=True, exist_ok=True)
    return [ConversionJob(Path(args.input), single_output)]


def convert_csv_file(
    input_path: str | Path,
    output_path: str | Path,
    meta_cfg: MetaConfig,
    *,
    source_label: str | None = None,
) -> Path:
    input_path = Path(input_path)
    parsed = parse_csv(str(input_path))
    if not parsed.devices:
        raise ValueError(f"No device rows detected in {input_path}")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    timestamps = [_device_timestamp(device.metadata) for device in parsed.devices]
    setup_time = min(timestamps)
    finish_time = max(timestamps)

    with output_path.open("wb") as stream:
        stdf = stdf_writer.BinaryRecordWriter(stream)
        stdf.write(stdf_writer.FAR, {"CPU_TYPE": 2, "STDF_VER": 4})

        invoker = source_label or Path(sys.argv[0]).name
        atr_messages = [f"csv_to_stdf {invoker} input={Path(input_path).name}"] + meta_cfg.atr_entries
        now = int(time.time())
        for message in atr_messages:
            stdf.write(stdf_writer.ATR, {"MOD_TIM": now, "CMD_LINE": message})

        mir_values = build_mir_values(parsed, setup_time, meta_cfg)
        stdf.write(stdf_writer.MIR, mir_values)

        for device, device_ts in zip(parsed.devices, timestamps):
            write_device_records(
                stdf,
                parsed,
                device,
                device_ts,
                head=meta_cfg.head_number,
                site=meta_cfg.site_number,
            )

        stdf.write(
            stdf_writer.MRR,
            {
                "FINISH_T": finish_time,
                "DISP_COD": "P" if _all_passed(parsed.devices) else "F",
                "USR_DESC": "CSV to STDF conversion complete",
                "EXC_DESC": "",
            },
        )

    return output_path


def build_mir_values(parsed: ParsedCsv, setup_time: int, meta_cfg: MetaConfig) -> Dict[str, object]:
    first_meta = parsed.devices[0].metadata
    mir_values: Dict[str, object] = {
        "SETUP_T": setup_time,
        "START_T": setup_time,
        "STAT_NUM": 1,
        "MODE_COD": (first_meta.get("TEST_MODE") or "P")[:1],
        "LOT_ID": first_meta.get("LOT_ID", "UNKNOWN"),
        "PART_TYP": first_meta.get("PRODUCT_PART", ""),
        "NODE_NAM": first_meta.get("Test_Location", ""),
        "TSTR_TYP": first_meta.get("TESTER_TYPE", first_meta.get("TESTER", "")),
        "JOB_NAM": first_meta.get("TEST_PROGRAM", first_meta.get("Test_Name", "")),
        "JOB_REV": first_meta.get("REVISION", ""),
        "OPER_NAM": first_meta.get("SFIS_State", ""),
        "EXEC_TYP": first_meta.get("Model", ""),
        "EXEC_VER": first_meta.get("TESTER", ""),
        "TEST_COD": first_meta.get("Test_Name", ""),
        "TST_TEMP": first_meta.get("Station", ""),
        "USER_TXT": "Generated via csv_to_stdf",
        "PKG_TYP": first_meta.get("Package_Type", ""),
        "FAMLY_ID": first_meta.get("PRODUCT_PART", ""),
        "DATE_COD": first_meta.get("DATE", ""),
        "FACIL_ID": first_meta.get("Test_Location", ""),
        "FLOOR_ID": first_meta.get("Station", ""),
        "PROC_ID": first_meta.get("TEST_PROGRAM", ""),
        "OPER_FRQ": first_meta.get("TEST_MODE", ""),
        "FLOW_ID": first_meta.get("Test_Type", ""),
        "SETUP_ID": first_meta.get("Test_Location", ""),
        "SERL_NUM": first_meta.get("TESTER", ""),
    }
    mir_values.update(meta_cfg.mir_overrides)
    return mir_values


def write_device_records(
    stdf: stdf_writer.BinaryRecordWriter,
    parsed: ParsedCsv,
    device,
    timestamp: int,
    head: int,
    site: int,
) -> None:
    metadata = device.metadata
    stdf.write(stdf_writer.PIR, {"HEAD_NUM": head, "SITE_NUM": site})

    executed_tests = 0
    for test_def in parsed.tests:
        raw_value = device.measurements.get(test_def.test_number)
        numeric_value = _parse_result_number(raw_value)
        if numeric_value is None:
            continue
        executed_tests += 1
        stdf.write(
            stdf_writer.PTR,
            {
                "TEST_NUM": test_def.test_number,
                "HEAD_NUM": head,
                "SITE_NUM": site,
                "TEST_FLG": 0,
                "PARM_FLG": 0,
                "RESULT": numeric_value,
                "TEST_TXT": test_def.name,
                "UNITS": test_def.unit or "",
                "LO_LIMIT": _limit_or_nan(test_def.lower_limit),
                "HI_LIMIT": _limit_or_nan(test_def.upper_limit),
                "LO_SPEC": _limit_or_nan(test_def.lower_limit),
                "HI_SPEC": _limit_or_nan(test_def.upper_limit),
                "RES_SCAL": 0,
                "LLM_SCAL": 0,
                "HLM_SCAL": 0,
                "OPT_FLAG": 0,
                "ALARM_ID": metadata.get("Error Code", ""),
            },
        )

    prr_payload = {
        "HEAD_NUM": head,
        "SITE_NUM": site,
        "PART_FLG": 0 if _is_pass(metadata) else 1,
        "NUM_TEST": executed_tests,
        "HARD_BIN": 1 if _is_pass(metadata) else 255,
        "SOFT_BIN": _parse_int(metadata.get("Error Code")) or (1 if _is_pass(metadata) else 255),
        "X_COORD": _parse_int(metadata.get("X_CID")) or 0,
        "Y_COORD": _parse_int(metadata.get("Y_CID")) or 0,
        "TEST_T": int(float(metadata.get("Test Time", "0") or 0)),
        "PART_ID": _resolve_part_id(metadata),
        "PART_TXT": metadata.get("PRODUCT_PART", ""),
        "PART_FIX": b"",
    }
    stdf.write(stdf_writer.PRR, prr_payload)


def _all_passed(devices) -> bool:
    return all(_is_pass(device.metadata) for device in devices)


def _is_pass(metadata: Dict[str, str]) -> bool:
    return (metadata.get("Test Result") or "").strip().upper() == "PASS"


def _parse_result_number(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _limit_or_nan(value: float | None) -> float:
    return value if value is not None else float("nan")


def _parse_int(value: str | None) -> int | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def _resolve_part_id(metadata: Dict[str, str]) -> str:
    for key in ("DMC_string", "IC_serial_CID", "IC_DEVICE_ID_CID", "product_id_CID", "Test_CID"):
        if metadata.get(key):
            return metadata[key]
    return metadata.get("PRODUCT_PART", "")


def _device_timestamp(metadata: Dict[str, str]) -> int:
    raw = metadata.get("DATE")
    if raw:
        for fmt in ("%Y%m%d_%H%M%S", "%Y-%m-%d %H:%M:%S"):
            try:
                dt = datetime.strptime(raw, fmt)
                return int(dt.replace(tzinfo=timezone.utc).timestamp())
            except ValueError:
                continue
    return int(time.time())


if __name__ == "__main__":
    main()
