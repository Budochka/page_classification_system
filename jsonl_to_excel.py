#!/usr/bin/env python3
"""Convert JSONL results file to Excel (.xlsx) format."""

import json
import sys
from pathlib import Path

try:
    import pandas as pd
except ImportError:
    print("ERROR: pandas and openpyxl are required.")
    print("Install with: pip install pandas openpyxl")
    sys.exit(1)


def jsonl_to_excel(jsonl_path: str, excel_path: str | None = None) -> None:
    """
    Convert JSONL file to Excel format.
    
    Args:
        jsonl_path: Path to input JSONL file
        excel_path: Path to output Excel file (default: same name with .xlsx extension)
    """
    jsonl_file = Path(jsonl_path)
    if not jsonl_file.exists():
        print(f"ERROR: File not found: {jsonl_path}")
        sys.exit(1)
    
    if excel_path is None:
        excel_path = jsonl_file.with_suffix(".xlsx")
    else:
        excel_path = Path(excel_path)
    
    # Read JSONL file
    records = []
    with open(jsonl_file, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                records.append(record)
            except json.JSONDecodeError as e:
                print(f"WARNING: Skipping invalid JSON on line {line_num}: {e}")
                continue
    
    if not records:
        print("ERROR: No valid records found in JSONL file")
        sys.exit(1)
    
    # Convert to DataFrame
    df = pd.DataFrame(records)
    
    # Flatten nested fields for better Excel display
    # Convert list fields to comma-separated strings
    for col in df.columns:
        if df[col].dtype == 'object':
            # Check if column contains lists
            if df[col].apply(lambda x: isinstance(x, list)).any():
                df[col] = df[col].apply(
                    lambda x: ", ".join(str(v) for v in x) if isinstance(x, list) else str(x) if x is not None else ""
                )
    
    # Write to Excel
    df.to_excel(excel_path, index=False, engine='openpyxl')
    print(f"✓ Converted {len(records)} records from {jsonl_file.name} to {excel_path.name}")
    print(f"  Output file: {excel_path.absolute()}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python jsonl_to_excel.py <input.jsonl> [output.xlsx]")
        print("\nExample:")
        print("  python jsonl_to_excel.py output/results.jsonl")
        print("  python jsonl_to_excel.py output/results.jsonl output/results.xlsx")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    jsonl_to_excel(input_file, output_file)
