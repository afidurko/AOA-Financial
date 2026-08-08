"""Vault schema — note types and property contracts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class PropertySpec:
    name: str
    type: str
    source: str
    refresh: str = "every_run"


@dataclass
class VaultSchema:
    note_types: dict[str, list[PropertySpec]]

    def properties_for(self, note_type: str) -> list[PropertySpec]:
        return list(self.note_types.get(note_type, []))


def load_schema(schema_path: Path) -> VaultSchema:
    if not schema_path.is_file():
        return VaultSchema(note_types={})
    data = yaml.safe_load(schema_path.read_text(encoding="utf-8")) or {}
    note_types: dict[str, list[PropertySpec]] = {}
    for note_type, props in (data.get("note_types") or {}).items():
        if not isinstance(props, list):
            continue
        specs: list[PropertySpec] = []
        for row in props:
            if not isinstance(row, dict) or "name" not in row:
                continue
            specs.append(
                PropertySpec(
                    name=str(row["name"]),
                    type=str(row.get("type", "string")),
                    source=str(row.get("source", "")),
                    refresh=str(row.get("refresh", "every_run")),
                )
            )
        note_types[str(note_type)] = specs
    return VaultSchema(note_types=note_types)


def default_schema_path(vault_root: Path) -> Path:
    return vault_root / "_schema.yaml"
