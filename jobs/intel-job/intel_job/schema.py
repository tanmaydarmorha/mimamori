"""The model-facing schema: `schemas/playbook.json` with every cross-file `$ref` resolved, minus the
fields only code may set (status, version, sources, approval). The model cannot even emit `status`."""

from __future__ import annotations

import copy
import json
from typing import Any

from mimamori_common.schemas import schemas_dir

CODE_OWNED = ("version", "status", "sources", "approved_by", "approved_at")
_DROP_KEYS = {"$schema", "$id", "$defs", "description"}


def bundle(name: str = "playbook.json") -> dict:
    """Resolve `#/...` and `other.json#/...` refs (common's `inline_refs` rejects cross-file refs)."""
    base = schemas_dir()
    docs: dict[str, dict] = {}

    def doc(file: str) -> dict:
        if file not in docs:
            docs[file] = json.loads((base / file).read_text(encoding="utf-8"))
        return docs[file]

    def follow(file: str, pointer: str) -> Any:
        target: Any = doc(file)
        for part in filter(None, pointer.lstrip("#").split("/")):
            target = target[part]
        return target

    def resolve(node: Any, file: str) -> Any:
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str):
                ref_file, _, pointer = ref.partition("#")
                target_file = ref_file or file
                inner = resolve(copy.deepcopy(follow(target_file, pointer)), target_file)
                return {**inner, **{k: v for k, v in node.items() if k not in ("$ref", "description")}}
            return {k: resolve(v, file) for k, v in node.items() if k not in _DROP_KEYS}
        if isinstance(node, list):
            return [resolve(v, file) for v in node]
        return node

    return resolve(doc(name), name)


def model_schema() -> dict:
    schema = bundle()
    for field in CODE_OWNED:
        schema["properties"].pop(field, None)
    schema["required"] = [r for r in schema["required"] if r not in CODE_OWNED]
    return schema
