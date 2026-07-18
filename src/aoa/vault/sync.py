"""Vault sync engine — analyze and update every property in the vault tree."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aoa.vault.analyzers import AnalyzerContext, engineering_l2_enabled, run_analyzer
from aoa.vault.schema import VaultSchema, default_schema_path, load_schema
from aoa.vault.store import (
    VaultNote,
    apply_property_updates,
    list_notes,
    read_note,
    write_note,
)


@dataclass
class NoteSyncResult:
    path: str
    note_type: str
    changed: dict[str, tuple[Any, Any]] = field(default_factory=dict)
    skipped: bool = False
    reason: str = ""


@dataclass
class VaultSyncResult:
    dry_run: bool
    notes_scanned: int = 0
    notes_updated: int = 0
    notes_created: int = 0
    properties_changed: int = 0
    note_results: list[NoteSyncResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_context(self) -> dict[str, Any]:
        return {
            "dry_run": self.dry_run,
            "notes_scanned": self.notes_scanned,
            "notes_updated": self.notes_updated,
            "notes_created": self.notes_created,
            "properties_changed": self.properties_changed,
            "note_results": [
                {
                    "path": r.path,
                    "note_type": r.note_type,
                    "changed": {k: {"old": v[0], "new": v[1]} for k, v in r.changed.items()},
                    "skipped": r.skipped,
                    "reason": r.reason,
                }
                for r in self.note_results
            ],
            "errors": self.errors,
        }


def resolve_vault_root(config: Any, repo_root: Path | None = None) -> Path:
    root = repo_root or _find_repo_root()
    rel = getattr(config, "vault_path", "vault") or "vault"
    path = Path(rel)
    if not path.is_absolute():
        path = root / path
    return path


def sync_vault(
    config: Any,
    *,
    repo_root: Path | None = None,
    dry_run: bool = False,
    cycle_ctx: Any | None = None,
    workloop_extracted: dict[str, Any] | None = None,
    run_verify: bool = False,
    note_filter: set[str] | None = None,
    create_symbols: bool = True,
) -> VaultSyncResult:
    """Walk the vault tree, analyze every property, and apply updates."""
    root = repo_root or _find_repo_root()
    vault_root = resolve_vault_root(config, root)
    schema = load_schema(default_schema_path(vault_root))
    result = VaultSyncResult(dry_run=dry_run)

    if not getattr(config, "vault_sync_enabled", True):
        result.errors.append("vault sync disabled")
        return result

    repair_path = getattr(config, "repair_path", None)
    analyzer_ctx = AnalyzerContext(
        repo_root=root,
        vault_root=vault_root,
        cycle_ctx=cycle_ctx,
        workloop_extracted=workloop_extracted or {},
        run_verify=run_verify,
        repair_path=Path(repair_path) if repair_path else None,
    )

    paths = list_notes(vault_root)
    if create_symbols and cycle_ctx is not None:
        paths.extend(_ensure_symbol_notes(vault_root, cycle_ctx, paths))

    for path in paths:
        rel = str(path.relative_to(vault_root))
        if note_filter is not None and rel not in note_filter:
            continue
        note_result = _sync_note(path, schema, analyzer_ctx, dry_run=dry_run)
        result.notes_scanned += 1
        if note_result.skipped:
            result.note_results.append(note_result)
            continue
        if note_result.changed:
            result.notes_updated += 1
            result.properties_changed += len(note_result.changed)
        result.note_results.append(note_result)

    return result


def sync_vault_from_cycle(cycle_ctx: Any, *, dry_run: bool = False) -> VaultSyncResult:
    return sync_vault(
        cycle_ctx.config,
        repo_root=_find_repo_root(),
        dry_run=dry_run,
        cycle_ctx=cycle_ctx,
        create_symbols=True,
    )


def sync_vault_from_workloop(
    config: Any,
    *,
    repo_root: Path,
    extracted: dict[str, Any],
    dry_run: bool = False,
) -> VaultSyncResult:
    filter_paths = {
        "loops/engineering.md",
        "loops/workloop.md",
        "system/health.md",
    }
    return sync_vault(
        config,
        repo_root=repo_root,
        dry_run=dry_run,
        workloop_extracted=extracted,
        note_filter=filter_paths,
        create_symbols=False,
    )


def sync_vault_engineering(
    config: Any,
    *,
    repo_root: Path | None = None,
    dry_run: bool | None = None,
    run_verify: bool = True,
) -> VaultSyncResult:
    root = repo_root or _find_repo_root()
    if dry_run is None:
        dry_run = not engineering_l2_enabled(root)
    filter_paths = {
        "loops/engineering.md",
        "loops/workloop.md",
        "system/health.md",
        "trading/cycle-latest.md",
        "brain/mesh.md",
    }
    return sync_vault(
        config,
        repo_root=root,
        dry_run=dry_run,
        run_verify=run_verify,
        note_filter=filter_paths,
        create_symbols=False,
    )


def vault_status(config: Any, *, repo_root: Path | None = None) -> dict[str, Any]:
    """Report property staleness without writing."""
    sync_result = sync_vault(
        config,
        repo_root=repo_root,
        dry_run=True,
        run_verify=False,
        create_symbols=False,
    )
    stale = [
        {
            "path": r.path,
            "note_type": r.note_type,
            "would_change": list(r.changed.keys()),
        }
        for r in sync_result.note_results
        if r.changed
    ]
    return {
        "vault_root": str(resolve_vault_root(config, repo_root)),
        "notes_scanned": sync_result.notes_scanned,
        "stale_notes": stale,
        "stale_count": len(stale),
    }


def _sync_note(
    path: Path,
    schema: VaultSchema,
    ctx: AnalyzerContext,
    *,
    dry_run: bool,
) -> NoteSyncResult:
    note = read_note(path)
    note_type = note.note_type
    if not note_type:
        return NoteSyncResult(
            path=str(path),
            note_type="",
            skipped=True,
            reason="missing type in frontmatter",
        )

    specs = schema.properties_for(note_type)
    if not specs:
        return NoteSyncResult(
            path=str(path),
            note_type=note_type,
            skipped=True,
            reason=f"unknown note type {note_type!r}",
        )

    ctx.note_path = path
    ctx.note_type = note_type
    updates: dict[str, Any] = {}
    for spec in specs:
        analyzed = run_analyzer(spec.source, ctx)
        if spec.name in analyzed:
            updates[spec.name] = analyzed[spec.name]

    changed = apply_property_updates(note, updates)
    if changed and not dry_run:
        write_note(note)

    return NoteSyncResult(path=str(path), note_type=note_type, changed=changed)


def _ensure_symbol_notes(
    vault_root: Path,
    cycle_ctx: Any,
    existing: list[Path],
) -> list[Path]:
    symbols_dir = vault_root / "trading" / "symbols"
    symbols_dir.mkdir(parents=True, exist_ok=True)
    existing_stems = {p.stem.upper() for p in existing}
    created: list[Path] = []
    for symbol in cycle_ctx.blackboard.environment.meshed_views:
        sym = symbol.upper()
        if sym in existing_stems:
            continue
        path = symbols_dir / f"{sym}.md"
        note = VaultNote(
            path=path,
            frontmatter={"type": "symbol", "ticker": sym, "locked": []},
            body=f"\n# {sym}\n\nAuto-synced symbol view from the trading swarm.\n",
        )
        write_note(note)
        created.append(path)
        existing_stems.add(sym)
    return created


def _find_repo_root() -> Path:
    here = Path.cwd()
    for parent in [here, *here.parents]:
        if (parent / "pyproject.toml").is_file() and (parent / "src" / "aoa").is_dir():
            return parent
    return here
