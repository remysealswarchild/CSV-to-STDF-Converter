"""Minimal STDF v4 binary writer used by the CSV converter."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Sequence, Tuple, Union
import struct


@dataclass(frozen=True)
class RecordDef:
    """Describes the numeric id and field layout of an STDF record."""

    name: str
    typ: int
    sub: int
    field_map: Sequence[Tuple[str, str]]


_PACK_FORMATS: Dict[str, str] = {
    "U1": "<B",
    "U2": "<H",
    "U4": "<I",
    "I1": "<b",
    "I2": "<h",
    "I4": "<i",
    "R4": "<f",
    "B1": "<B",
}


class BinaryRecordWriter:
    """Serialises STDF record payloads and writes them with the proper header."""

    def __init__(self, stream):
        self._stream = stream

    def write(self, record: RecordDef, values: Dict[str, Union[str, int, float, bytes, bytearray, Iterable[int]]]):
        """Write a complete record, padding missing fields with sensible defaults."""

        payload = bytearray()
        for field_name, field_type in record.field_map:
            payload.extend(self._encode_field(field_type, values.get(field_name)))
        header = struct.pack("<HBB", len(payload), record.typ, record.sub)
        self._stream.write(header)
        self._stream.write(payload)

    def _encode_field(self, field_type: str, value):
        if field_type in _PACK_FORMATS:
            pack_fmt = _PACK_FORMATS[field_type]
            return struct.pack(pack_fmt, self._normalise_numeric(field_type, value))
        if field_type == "C1":
            return self._encode_c1(value)
        if field_type == "Cn":
            return self._encode_cn(value)
        if field_type == "Bn":
            return self._encode_bn(value)
        raise ValueError(f"Unsupported STDF field type: {field_type}")

    @staticmethod
    def _normalise_numeric(field_type: str, value):
        if value is None:
            if field_type.startswith("I") or field_type.startswith("R"):
                return 0
            return 0
        if isinstance(value, bool):
            return int(value)
        if field_type.startswith("R"):
            if isinstance(value, str) and value.strip() == "":
                return 0.0
            return float(value)
        if isinstance(value, str) and value.strip() == "":
            return 0
        return int(value)

    @staticmethod
    def _encode_c1(value) -> bytes:
        char = (value or " ")
        if isinstance(char, str):
            if len(char) == 0:
                char = " "
            char = char[0]
            data = char.encode("ascii", errors="ignore") or b" "
        else:
            data = bytes([char])[:1]
        return data

    @staticmethod
    def _encode_cn(value) -> bytes:
        if value is None:
            return b"\x00"
        if isinstance(value, bytes):
            data = value[:255]
        else:
            text = str(value)
            data = text.encode("ascii", errors="ignore")[:255]
        return struct.pack("<B", len(data)) + data

    @staticmethod
    def _encode_bn(value) -> bytes:
        if value is None:
            return b"\x00"
        if isinstance(value, (bytes, bytearray)):
            data = bytes(value)
        else:
            data = bytes(int(v) & 0xFF for v in value)
        if len(data) > 255:
            data = data[:255]
        return struct.pack("<B", len(data)) + data


FAR = RecordDef(
    "FAR",
    0,
    10,
    (("CPU_TYPE", "U1"), ("STDF_VER", "U1")),
)

ATR = RecordDef(
    "ATR",
    0,
    20,
    (("MOD_TIM", "U4"), ("CMD_LINE", "Cn")),
)

MIR = RecordDef(
    "MIR",
    1,
    10,
    (
        ("SETUP_T", "U4"),
        ("START_T", "U4"),
        ("STAT_NUM", "U1"),
        ("MODE_COD", "C1"),
        ("RTST_COD", "C1"),
        ("PROT_COD", "C1"),
        ("BURN_TIM", "U2"),
        ("CMOD_COD", "C1"),
        ("LOT_ID", "Cn"),
        ("PART_TYP", "Cn"),
        ("NODE_NAM", "Cn"),
        ("TSTR_TYP", "Cn"),
        ("JOB_NAM", "Cn"),
        ("JOB_REV", "Cn"),
        ("SBLOT_ID", "Cn"),
        ("OPER_NAM", "Cn"),
        ("EXEC_TYP", "Cn"),
        ("EXEC_VER", "Cn"),
        ("TEST_COD", "Cn"),
        ("TST_TEMP", "Cn"),
        ("USER_TXT", "Cn"),
        ("AUX_FILE", "Cn"),
        ("PKG_TYP", "Cn"),
        ("FAMLY_ID", "Cn"),
        ("DATE_COD", "Cn"),
        ("FACIL_ID", "Cn"),
        ("FLOOR_ID", "Cn"),
        ("PROC_ID", "Cn"),
        ("OPER_FRQ", "Cn"),
        ("SPEC_NAM", "Cn"),
        ("SPEC_VER", "Cn"),
        ("FLOW_ID", "Cn"),
        ("SETUP_ID", "Cn"),
        ("DSGN_REV", "Cn"),
        ("ENG_ID", "Cn"),
        ("ROM_COD", "Cn"),
        ("SERL_NUM", "Cn"),
        ("SUPR_NAM", "Cn"),
    ),
)

PIR = RecordDef(
    "PIR",
    5,
    10,
    (("HEAD_NUM", "U1"), ("SITE_NUM", "U1")),
)

PTR = RecordDef(
    "PTR",
    15,
    10,
    (
        ("TEST_NUM", "U4"),
        ("HEAD_NUM", "U1"),
        ("SITE_NUM", "U1"),
        ("TEST_FLG", "B1"),
        ("PARM_FLG", "B1"),
        ("RESULT", "R4"),
        ("TEST_TXT", "Cn"),
        ("ALARM_ID", "Cn"),
        ("OPT_FLAG", "B1"),
        ("RES_SCAL", "I1"),
        ("LLM_SCAL", "I1"),
        ("HLM_SCAL", "I1"),
        ("LO_LIMIT", "R4"),
        ("HI_LIMIT", "R4"),
        ("UNITS", "Cn"),
        ("C_RESFMT", "Cn"),
        ("C_LLMFMT", "Cn"),
        ("C_HLMFMT", "Cn"),
        ("LO_SPEC", "R4"),
        ("HI_SPEC", "R4"),
    ),
)

PRR = RecordDef(
    "PRR",
    5,
    20,
    (
        ("HEAD_NUM", "U1"),
        ("SITE_NUM", "U1"),
        ("PART_FLG", "B1"),
        ("NUM_TEST", "U2"),
        ("HARD_BIN", "U2"),
        ("SOFT_BIN", "U2"),
        ("X_COORD", "I2"),
        ("Y_COORD", "I2"),
        ("TEST_T", "U4"),
        ("PART_ID", "Cn"),
        ("PART_TXT", "Cn"),
        ("PART_FIX", "Bn"),
    ),
)

MRR = RecordDef(
    "MRR",
    1,
    20,
    (("FINISH_T", "U4"), ("DISP_COD", "C1"), ("USR_DESC", "Cn"), ("EXC_DESC", "Cn")),
)
