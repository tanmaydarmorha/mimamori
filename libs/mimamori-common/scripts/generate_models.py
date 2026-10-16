"""Regenerate mimamori_common/models/generated/ from schemas/*.json.

Usage (repo root):  python libs/mimamori-common/scripts/generate_models.py
Needs `pip install datamodel-code-generator`. CI re-runs this and fails on drift, so never edit the
generated files by hand: change the schema, then regenerate.
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "libs/mimamori-common/src/mimamori_common/models/generated"


def main():
    with tempfile.TemporaryDirectory() as tmp:
        schemas = Path(tmp) / "schemas"
        schemas.mkdir()
        for path in sorted((ROOT / "schemas").glob("*.json")):
            shutil.copy(path, schemas / path.name)
        if OUT.exists():
            shutil.rmtree(OUT)
        subprocess.run(
            [
                sys.executable, "-m", "datamodel_code_generator",
                "--input", str(schemas), "--input-file-type", "jsonschema",
                "--output", str(OUT),
                "--output-model-type", "pydantic_v2.BaseModel",
                "--use-annotated", "--target-python-version", "3.12",
                "--disable-timestamp", "--formatters", "ruff-format",
            ],
            check=True,
        )
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
