# CSV → STDF v4 Converter

This repository contains a Python utility that transforms the supplied production CSV dump into a standards-compliant STDF v4 datalog. The current CSV ("Selene" format) stores metadata in the first two rows (`Test_Name`, `Test_Number`, `Lower_Limit`, `Upper_Limit`, `Unit`, …) followed by one row per device under test. The converter reads that layout, emits the appropriate STDF records, and leaves room for additional metadata through configuration so you can extend it without rewriting core logic.

## Repository Layout

| Path | Purpose |
| --- | --- |
| `csv_to_stdf.py` | CLI entry point; orchestrates CSV parsing, metadata assembly, STDF writing, and batch jobs. |
| `gui_app.py` | Tkinter GUI that batches CSV files without touching the command line. |
| `stdf_converter/csv_parser.py` | Understands the multi-row CSV header, extracts measurement definitions, and returns per-device records. |
| `stdf_converter/writer.py` | Minimal STDF v4 binary writer plus record definitions (FAR, ATR, MIR, PIR, PTR, PRR, MRR). |
| `requirements.txt` | Place to pin dependencies (currently just notes that we use the standard library). |

## How the Data Flows

1. **CSV ingestion** – `csv_parser.py` reads every column, classifies metadata vs. measurements using the `Test_Number` row, and captures limits/units.
2. **Record assembly** – `csv_to_stdf.py` uses the parsed structure to build:
   - FAR (file attributes) and ATR (tool history) records.
   - MIR (lot-level metadata) populated from CSV fields + optional overrides.
   - For every device row: PIR, one PTR per populated measurement, and a PRR summarizing pass/fail, bins, coordinates, etc.
   - A final MRR summarizing lot completion.
3. **Binary output** – `writer.py` serializes each record with STDF-compliant headers and payloads.

## Prerequisites

- Python 3.11 (already provided via `.venv`).
- `pip` (bundled with the Python interpreter) so you can install from `requirements.txt`.
- Tkinter (bundled with standard CPython on Windows/macOS; install `python3-tk` on Linux distros) for the GUI.
- Windows PowerShell is assumed for the commands below; translate to your shell if needed.

### Install Dependencies

Even though the converter currently relies only on the standard library, keep your environment in sync with future updates by installing from `requirements.txt`:

```powershell
D:/converter/.venv/Scripts/python.exe -m pip install -r requirements.txt
```

### Activate / Use the Virtual Environment

You can run the converter directly through the virtual environment interpreter without activating it:

```powershell
D:/converter/.venv/Scripts/python.exe --version
```

Use that interpreter for every command to ensure consistent dependencies.

## Running the Converter (Step by Step)

1. Place your source CSV anywhere convenient (use `--input` to point at it explicitly).
2. Optionally prepare a metadata JSON file (see [Metadata Overrides](#metadata-overrides)).
3. Run the converter:

```powershell
D:/converter/.venv/Scripts/python.exe csv_to_stdf.py `
  --input "lot1.csv" `
  --output "lot1.stdf" `
  --meta "meta.json"      # optional
```

4. Inspect the console output (it reports the target STDF path).
5. Consume `sample.stdf` with your STDF viewer, or keep it for downstream flows.

### CLI Arguments

| Flag | Default | Description |
| --- | --- | --- |
| `--input` | `input.csv` | Path to the Selene-format CSV file. |
| `--output` | `out.stdf` | Destination STDF v4 binary file. |
| `--meta` | _unset_ | Optional JSON file describing MIR overrides, ATR notes, and head/site IDs. |
| `--head` | `1` | Default test head number (used when CSV lacks that info). |
| `--site` | `1` | Default site number. |
| `--inputs` | _unset_ | Provide multiple CSV paths to convert in one run (overrides `--input`). |
| `--output-dir` | `.` | Destination directory for generated STDF files when using `--inputs`. |

If the `--meta` file provides `head_number` / `site_number`, they override the CLI defaults.

### Batch Conversion

Use `--inputs` to process multiple CSV files at once. Each CSV is written to the folder provided by `--output-dir` (created automatically) while retaining the source filename stem:

```powershell
D:/converter/.venv/Scripts/python.exe csv_to_stdf.py `
  --inputs "lot1.csv" "lot2.csv" "lot3.csv" `
  --output-dir "artifacts" `
  --meta "meta.json"
```

All jobs share the same metadata overrides, head, and site defaults. If any file fails, the CLI reports the failures but continues processing the rest.

## Metadata Overrides

You can add lot-level context without changing code by supplying a JSON document to `--meta`. Supported keys:

- `head_number` / `site_number` (ints) – apply to PIR/PTR/PRR records.
- `mir_overrides` (object) – any MIR field name → value. Examples: `MODE_COD`, `OPER_NAM`, `FLOW_ID`, etc.
- `atr_entries` (array of strings) – extra ATR records appended after the default command-tracking entry.

Example:

```json
{
  "head_number": 2,
  "site_number": 3,
  "mir_overrides": {
    "MODE_COD": "E",
    "OPER_NAM": "Engineering",
    "FLOW_ID": "BringUp"
  },
  "atr_entries": [
    "Batch=LOT42",
    "Build=2025-11-17"
  ]
}
```

Save this as `meta.json`, then run:

```powershell
D:/converter/.venv/Scripts/python.exe csv_to_stdf.py --input prod.csv --output prod.stdf --meta meta.json
```

## CSV Expectations

- Row 1 (`Test_Name`) supplies human-readable column names.
- Row 2 (`Test_Number`) identifies measurement columns; blanks are treated as metadata.
- Rows 3–5 supply `Lower_Limit`, `Upper_Limit`, and `Unit` values per test.
- Row 6 onward contains device rows. Each row must include at least `Test Result`, `DATE`, `LOT_ID`, and any other metadata you want mirrored into the MIR/PRR records.
- Additional measurement columns are auto-detected as long as they have numeric `Test_Number` values.

## STDF Records Generated

- **FAR** – CPU type (`2` = little endian) and STDF version (`4`).
- **ATR** – always includes one entry for the converter invocation plus any user-supplied notes.
- **MIR** – populated from CSV metadata with optional overrides.
- **PIR** – emitted per device row to mark the start of testing for that device.
- **PTR** – one per populated measurement; carries result, limits, units, and optional alarm ID.
- **PRR** – summarizes per-device outcome, bins, coordinates, elapsed time, and identifiers.
- **MRR** – closes the stream and marks overall pass/fail (based on whether every device row passed).

## Validation & Troubleshooting

1. Re-run the converter after any CSV or code change.
2. Open the resulting STDF file with your preferred STDF viewer/dump tool to confirm record contents.
3. If the script reports "No device rows detected": ensure your CSV still contains the multi-row header.
4. If limits/units look wrong, verify the `Lower_Limit`/`Upper_Limit`/`Unit` rows match the measurement columns.

## Extending the Converter

- **New metadata fields** – edit `build_mir_values` (in `csv_to_stdf.py`) to map new CSV columns to MIR fields; add more PRR/PTR fields in `write_device_records` as needed.
- **Different CSV layout** – update `stdf_converter/csv_parser.py` to describe the new structure; the rest of the pipeline is agnostic as long as `ParsedCsv` exposes metadata, tests, and device rows.
- **Additional STDF records** – declare new `RecordDef` entries in `stdf_converter/writer.py` and emit them from the CLI.

## Graphical Interface

Prefer not to live in the terminal? Run the Tkinter GUI located in `gui_app.py`. It lets you:

- Queue multiple CSV files via a file picker (remove or clear entries as needed).
- Choose an output directory and optional metadata JSON file.
- Override head/site defaults.
- Monitor progress and errors in the built-in log window.

Launch it with:

```powershell
D:/converter/.venv/Scripts/python.exe gui_app.py
```

## Quick Reference Commands

```powershell
# Show help
D:/converter/.venv/Scripts/python.exe csv_to_stdf.py --help

# Convert a single CSV
D:/converter/.venv/Scripts/python.exe csv_to_stdf.py --input "lot1.csv" --output "lot1.stdf"

# Batch convert three CSVs
D:/converter/.venv/Scripts/python.exe csv_to_stdf.py --inputs "lot1.csv" "lot2.csv" "lot3.csv" --output-dir "artifacts"

# Launch the GUI
D:/converter/.venv/Scripts/python.exe gui_app.py
```

Keep this README close by for the exact flag names and expected file layout as you iterate on the converter.
