"""Download the Wind Turbine SCADA dataset from Kaggle and copy T1.csv into ./data.

Usage:  python scripts/download_data.py
"""
import shutil
from pathlib import Path

import kagglehub

DATASET = "berkerisen/wind-turbine-scada-dataset"
TARGET = Path(__file__).resolve().parent.parent / "data" / "T1.csv"


def main() -> None:
    cache_dir = Path(kagglehub.dataset_download(DATASET))
    source = next(cache_dir.rglob("T1.csv"))
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, TARGET)
    print(f"Copied {source} -> {TARGET}")


if __name__ == "__main__":
    main()
