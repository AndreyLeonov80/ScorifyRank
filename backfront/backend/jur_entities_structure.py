from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple
from xml.etree import ElementTree as ET


_NS_MAIN = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
_NS_REL = {"r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
_NS_PKG_REL = {"pr": "http://schemas.openxmlformats.org/package/2006/relationships"}
_CACHE_VERSION = 2


def analyze_jur_entity_structures(
    items: Iterable[Dict[str, Any]],
    *,
    app_dir: Path,
    cache_path: Path,
) -> Dict[str, Dict[str, Any]]:
    rows = [item for item in items if isinstance(item, dict)]
    cache = _load_cache(cache_path)
    cache_entries = cache.setdefault("entries", {})
    touched_cache_keys: set[str] = set()
    raw_results: Dict[str, Dict[str, Any]] = {}
    signature_counts: Dict[str, int] = {}

    for item in rows:
        file_key = str(item.get("file_key") or "").strip()
        rel_path = str(item.get("file_path") or "").strip()
        if not file_key or not rel_path:
            continue
        abs_path = _resolve_app_relative_path(app_dir, rel_path)
        if not abs_path.exists() or not abs_path.is_file():
            raw_results[file_key] = _make_missing_result()
            continue

        try:
            stat = abs_path.stat()
        except OSError:
            raw_results[file_key] = _make_missing_result()
            continue

        cache_key = _make_cache_key(abs_path, stat.st_size, stat.st_mtime)
        touched_cache_keys.add(cache_key)
        cached_entry = cache_entries.get(cache_key)
        if not isinstance(cached_entry, dict) or cached_entry.get("cache_version") != _CACHE_VERSION:
            cached_entry = _inspect_workbook(abs_path)
            cached_entry["cache_version"] = _CACHE_VERSION
            cache_entries[cache_key] = cached_entry
        raw_results[file_key] = dict(cached_entry)
        signature = str(cached_entry.get("structure_signature") or "").strip()
        if signature:
            signature_counts[signature] = signature_counts.get(signature, 0) + 1

    _prune_cache_entries(cache_entries, touched_cache_keys)
    _save_cache(cache_path, cache)

    dominant_signature = ""
    dominant_count = 0
    if signature_counts:
        dominant_signature, dominant_count = max(
            signature_counts.items(),
            key=lambda item: (item[1], item[0]),
        )

    results: Dict[str, Dict[str, Any]] = {}
    for item in rows:
        file_key = str(item.get("file_key") or "").strip()
        if not file_key:
            continue
        raw = raw_results.get(file_key) or _make_missing_result()
        signature = str(raw.get("structure_signature") or "").strip()
        same = bool(signature and dominant_signature and dominant_count >= 2 and signature == dominant_signature)
        results[file_key] = {
            "structure_signature": signature or None,
            "structure_summary": str(raw.get("structure_summary") or "").strip() or None,
            "structure_group_count": int(signature_counts.get(signature, 0)) if signature else 0,
            "structure_common": same,
            "structure_label": "Одинаковая" if same else "Разная",
            "structure_tone": "success" if same else "error",
        }
    return results


def _make_cache_key(path: Path, size_bytes: int, mtime_sec: float) -> str:
    return f"{path.resolve()}::{int(size_bytes)}::{int(mtime_sec)}"


def _resolve_app_relative_path(app_dir: Path, rel_path: str) -> Path:
    normalized = str(rel_path or "").strip()
    if normalized.startswith("/"):
        normalized = normalized[1:]
    return (app_dir / normalized).resolve()


def _load_cache(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"version": _CACHE_VERSION, "entries": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"version": _CACHE_VERSION, "entries": {}}
    if not isinstance(payload, dict):
        return {"version": _CACHE_VERSION, "entries": {}}
    payload.setdefault("version", _CACHE_VERSION)
    payload.setdefault("entries", {})
    return payload


def _save_cache(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _prune_cache_entries(entries: Dict[str, Any], keep_keys: set[str]) -> None:
    stale_keys = [key for key in entries.keys() if key not in keep_keys]
    for key in stale_keys:
        entries.pop(key, None)


def _make_missing_result() -> Dict[str, Any]:
    return {
        "structure_signature": "",
        "structure_summary": "Файл недоступен",
    }


def _inspect_workbook(path: Path) -> Dict[str, Any]:
    suffix = path.suffix.lower()
    if suffix == ".xls":
        return {
            "structure_signature": "legacy-xls",
            "structure_summary": "Legacy XLS",
        }
    if not zipfile.is_zipfile(path):
        return {
            "structure_signature": "not-a-zip-workbook",
            "structure_summary": "Не удалось распознать XLSX",
        }

    try:
        with zipfile.ZipFile(path) as zf:
            shared_strings = _read_shared_strings(zf)
            sheets = _read_ordered_sheet_entries(zf)
            sheet_descriptors: List[Dict[str, Any]] = []
            summary_parts: List[str] = []
            for idx, (title, member_name) in enumerate(sheets[:3], start=1):
                header_cells = _read_sheet_header_cells(zf, member_name, shared_strings)
                descriptor = {
                    "sheet_index": idx,
                    "header": header_cells[:20],
                    "columns": len(header_cells),
                }
                sheet_descriptors.append(descriptor)
                header_preview = ", ".join(header_cells[:6]) if header_cells else "без шапки"
                summary_parts.append(f"{title}: {header_preview}")

            signature_source = json.dumps(sheet_descriptors, ensure_ascii=False, sort_keys=True)
            signature = hashlib.sha1(signature_source.encode("utf-8")).hexdigest()
            summary = " | ".join(summary_parts) if summary_parts else "Пустая структура"
            return {
                "structure_signature": signature,
                "structure_summary": summary,
            }
    except Exception as exc:
        return {
            "structure_signature": f"error:{type(exc).__name__}",
            "structure_summary": f"Ошибка чтения: {type(exc).__name__}",
        }


def _read_shared_strings(zf: zipfile.ZipFile) -> List[str]:
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    values: List[str] = []
    for si in root.findall("x:si", _NS_MAIN):
        values.append(_collect_inline_text(si).strip())
    return values


def _read_ordered_sheet_entries(zf: zipfile.ZipFile) -> List[Tuple[str, str]]:
    workbook_root = ET.fromstring(zf.read("xl/workbook.xml"))
    rels_root = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    rels_map: Dict[str, str] = {}
    for rel in rels_root.findall("pr:Relationship", _NS_PKG_REL):
        rel_id = str(rel.attrib.get("Id") or "")
        target = str(rel.attrib.get("Target") or "")
        if rel_id and target:
            rels_map[rel_id] = "xl/" + target.lstrip("/")

    ordered: List[Tuple[str, str]] = []
    sheets_parent = workbook_root.find("x:sheets", _NS_MAIN)
    if sheets_parent is None:
        return ordered
    for sheet in sheets_parent.findall("x:sheet", _NS_MAIN):
        title = str(sheet.attrib.get("name") or "").strip() or "Sheet"
        rel_id = str(sheet.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id") or "")
        member = rels_map.get(rel_id)
        if member:
            ordered.append((title, member))
    return ordered


def _read_sheet_header_cells(zf: zipfile.ZipFile, member_name: str, shared_strings: List[str]) -> List[str]:
    root = ET.fromstring(zf.read(member_name))
    best_row: List[str] = []
    best_score = 0

    rows_parent = root.find("x:sheetData", _NS_MAIN)
    if rows_parent is None:
        return best_row

    for row in rows_parent.findall("x:row", _NS_MAIN)[:12]:
        values: List[str] = []
        for cell in row.findall("x:c", _NS_MAIN):
            value = _read_cell_text(cell, shared_strings)
            normalized = " ".join(str(value or "").split()).strip()
            if normalized:
                values.append(normalized)
        score = len(values)
        if score > best_score:
            best_row = values
            best_score = score
        if best_score >= 8:
            break
    return best_row


def _read_cell_text(cell: ET.Element, shared_strings: List[str]) -> str:
    cell_type = str(cell.attrib.get("t") or "").strip()
    if cell_type == "inlineStr":
        is_node = cell.find("x:is", _NS_MAIN)
        return _collect_inline_text(is_node).strip() if is_node is not None else ""
    if cell_type == "s":
        value_node = cell.find("x:v", _NS_MAIN)
        if value_node is None:
            return ""
        try:
            idx = int(str(value_node.text or "").strip())
        except Exception:
            return ""
        return shared_strings[idx] if 0 <= idx < len(shared_strings) else ""
    value_node = cell.find("x:v", _NS_MAIN)
    if value_node is not None and value_node.text is not None:
        return str(value_node.text)
    return _collect_inline_text(cell).strip()


def _collect_inline_text(node: ET.Element) -> str:
    return "".join(text for text in node.itertext() if text)
