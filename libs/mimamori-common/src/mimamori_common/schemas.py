"""Locate and load `schemas/*.json` at runtime (constrained decoding, validation, examples).

Search order: $MIMAMORI_SCHEMAS_DIR, /app/schemas (inside a container whose Dockerfile copies
`schemas/`), then `<repo>/schemas` relative to this file (editable installs).
"""

from __future__ import annotations

import copy
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from .config import Settings


def schemas_dir(settings: Settings | None = None) -> Path:
    candidates = []
    configured = (settings or Settings.from_env()).schemas_dir
    if configured:
        candidates.append(Path(configured))
    candidates.append(Path("/app/schemas"))
    candidates.append(Path(__file__).resolve().parents[4] / "schemas")
    for path in candidates:
        if (path / "copilot-turn.json").exists():
            return path
    raise FileNotFoundError(f"schemas/ not found; looked in {[str(c) for c in candidates]}. Set MIMAMORI_SCHEMAS_DIR.")


@lru_cache(maxsize=None)
def _load(directory: str, name: str) -> dict:
    return json.loads((Path(directory) / name).read_text())


def load_schema(name: str) -> dict:
    """`load_schema("copilot-turn.json")` returns a fresh copy."""
    return copy.deepcopy(_load(str(schemas_dir()), name))


def load_example(name: str) -> Any:
    """`load_example("playbooks.json")` from schemas/examples/."""
    return json.loads((schemas_dir() / "examples" / name).read_text())


def inline_refs(schema: dict) -> dict:
    """Resolve same-document `#/$defs/...` refs so constrained-decoding backends that don't follow
    `$ref` still get the full schema. Drops `$schema`, `$id` and `$defs` from the result."""
    root = copy.deepcopy(schema)

    def resolve(node):
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str) and ref.startswith("#/"):
                target: Any = root
                for part in ref[2:].split("/"):
                    target = target[part]
                merged = {**resolve(copy.deepcopy(target)), **{k: v for k, v in node.items() if k != "$ref"}}
                return merged
            if "$ref" in node:
                raise ValueError(f"cross-document $ref not supported for constrained decoding: {node['$ref']}")
            return {k: resolve(v) for k, v in node.items() if k not in {"$schema", "$id", "$defs"}}
        if isinstance(node, list):
            return [resolve(v) for v in node]
        return node

    return resolve(root)
