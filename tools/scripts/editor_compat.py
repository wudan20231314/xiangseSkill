#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CORE_ACTIONS = ["searchBook", "bookDetail", "chapterList", "chapterContent"]


@dataclass
class Risk:
    level: str
    code: str
    path: str
    message: str


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def pick_source(doc: Any) -> tuple[str, dict[str, Any], str]:
    """Return (alias, source_obj, mode[new|legacy])."""
    if not isinstance(doc, dict):
        raise ValueError("top-level JSON must be object")

    # legacy single-source shape
    legacy_keys = {"bookSourceName", "bookSourceUrl", "searchBook", "bookDetail"}
    if legacy_keys.intersection(doc.keys()):
        return "<root>", doc, "legacy"

    # new wrapper shape: { alias: { sourceName, ... } }
    if len(doc) == 1:
        alias = next(iter(doc.keys()))
        src = doc[alias]
        if isinstance(src, dict):
            return alias, src, "new"

    # best effort: pick first dict child with recognizable markers
    for k, v in doc.items():
        if not isinstance(v, dict):
            continue
        if "sourceName" in v or "bookSourceName" in v:
            return k, v, "new"

    raise ValueError("cannot locate source object in JSON")


def _to_str(v: Any) -> str:
    if v is None:
        return ""
    return str(v)


def _to_int(v: Any, default: int) -> int:
    try:
        return int(v)
    except Exception:
        return default


def _normalize_weight_to_str(v: Any, default: str = "9999") -> str:
    if isinstance(v, bool):
        return default
    if isinstance(v, int):
        if v <= 0:
            return default
        return str(v)
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return default
        try:
            iv = int(float(s))
            if iv <= 0:
                return default
            return str(iv)
        except Exception:
            return default
    return default


def normalize_source_for_2561(source: dict[str, Any], *, default_weight: str = "9999") -> tuple[dict[str, Any], list[str]]:
    out = copy.deepcopy(source)
    changes: list[str] = []

    old_weight = out.get("weight")
    new_weight = _normalize_weight_to_str(old_weight, default=default_weight)
    if old_weight != new_weight:
        out["weight"] = new_weight
        changes.append(f"weight:{old_weight!r}->{new_weight!r}")

    return out, changes


def _request_filters_to_str(filters: Any) -> str:
    if isinstance(filters, str):
        s = filters
        return s if s.endswith("\n") else s + "\n"

    if not isinstance(filters, list):
        return ""

    blocks: list[str] = []
    for group in filters:
        if not isinstance(group, dict):
            continue
        key = _to_str(group.get("key")).strip()
        if not key:
            key = "filter"
        lines = [key]
        items = group.get("items")
        if isinstance(items, list):
            for it in items:
                if not isinstance(it, dict):
                    continue
                title = _to_str(it.get("title")).strip()
                value = _to_str(it.get("value")).strip()
                if not title:
                    continue
                lines.append(f"{title}::{value}")
        blocks.append("\n".join(lines))

    if not blocks:
        return ""
    return "\n\n".join(blocks) + "\n"


def normalize_bookworld_requestfilters_to_string(bookworld: Any) -> Any:
    if not isinstance(bookworld, dict):
        return bookworld

    out = copy.deepcopy(bookworld)
    for _, action in out.items():
        if not isinstance(action, dict):
            continue
        mk = action.get("moreKeys")
        if not isinstance(mk, dict):
            continue
        if "requestFilters" in mk:
            mk["requestFilters"] = _request_filters_to_str(mk.get("requestFilters"))
    return out


def to_legacy_source(source: dict[str, Any]) -> dict[str, Any]:
    legacy: dict[str, Any] = {}
    legacy["bookSourceGroup"] = _to_str(source.get("bookSourceGroup") or "香色闺阁")
    legacy["bookSourceName"] = _to_str(source.get("bookSourceName") or source.get("sourceName"))
    legacy["bookSourceUrl"] = _to_str(source.get("bookSourceUrl") or source.get("sourceUrl"))
    legacy["enable"] = _to_int(source.get("enable"), 1)
    legacy["weight"] = _normalize_weight_to_str(source.get("weight"))

    ua = _to_str(source.get("httpUserAgent"))
    if not ua:
        hh = source.get("httpHeaders")
        if isinstance(hh, dict):
            ua = _to_str(hh.get("User-Agent"))
    if ua:
        legacy["httpUserAgent"] = ua

    if "lastModifyTime" in source:
        legacy["lastModifyTime"] = _to_str(source.get("lastModifyTime"))

    if isinstance(source.get("httpHeaders"), dict):
        legacy["httpHeaders"] = copy.deepcopy(source["httpHeaders"])

    for key in CORE_ACTIONS + ["bookWorld"]:
        if key in source:
            legacy[key] = copy.deepcopy(source[key])

    if "bookWorld" in legacy:
        legacy["bookWorld"] = normalize_bookworld_requestfilters_to_string(legacy["bookWorld"])

    return legacy


def _strip_action_for_ab(action: dict[str, Any], *, keep_host: bool, keep_valid_config: bool, keep_more_keys: bool) -> dict[str, Any]:
    out = copy.deepcopy(action)

    if not keep_host:
        out.pop("host", None)

    if keep_valid_config:
        if "validConfig" not in out:
            out["validConfig"] = ""
    else:
        out["validConfig"] = ""

    if not keep_more_keys:
        out.pop("moreKeys", None)

    return out


def build_ab_variants(source: dict[str, Any]) -> dict[str, dict[str, Any]]:
    base = copy.deepcopy(source)
    base["weight"] = _normalize_weight_to_str(base.get("weight"))

    def core_minimal(src: dict[str, Any], *, keep_host: bool, keep_valid_config: bool, keep_more_keys: bool) -> dict[str, Any]:
        out = copy.deepcopy(src)
        for key in CORE_ACTIONS:
            act = out.get(key)
            if isinstance(act, dict):
                out[key] = _strip_action_for_ab(
                    act,
                    keep_host=keep_host,
                    keep_valid_config=keep_valid_config,
                    keep_more_keys=keep_more_keys,
                )
        return out

    # A0: 极简模板：无 bookWorld、无 top-level httpHeaders、validConfig 空
    a0 = core_minimal(base, keep_host=False, keep_valid_config=False, keep_more_keys=False)
    a0.pop("bookWorld", None)
    a0.pop("httpHeaders", None)

    # A1: 在 A0 基础上仅加 bookWorld + requestFilters(字符串)
    a1 = copy.deepcopy(a0)
    bw = base.get("bookWorld")
    if isinstance(bw, dict):
        bw_min = copy.deepcopy(bw)
        bw_min = normalize_bookworld_requestfilters_to_string(bw_min)
        for _, act in bw_min.items():
            if not isinstance(act, dict):
                continue
            act.pop("host", None)
            act["validConfig"] = ""
            mk = act.get("moreKeys")
            if isinstance(mk, dict):
                rf = _request_filters_to_str(mk.get("requestFilters"))
                act["moreKeys"] = {"requestFilters": rf} if rf else {}
            else:
                act["moreKeys"] = {}
        a1["bookWorld"] = bw_min

    # A2: 在 A1 基础上仅加 top-level httpHeaders
    a2 = copy.deepcopy(a1)
    if isinstance(base.get("httpHeaders"), dict):
        a2["httpHeaders"] = copy.deepcopy(base["httpHeaders"])

    # A3: 在 A2 基础上加 host/validConfig/moreKeys/removeHtmlKeys
    a3 = core_minimal(base, keep_host=True, keep_valid_config=True, keep_more_keys=True)
    if isinstance(a3.get("bookWorld"), dict):
        a3["bookWorld"] = normalize_bookworld_requestfilters_to_string(a3["bookWorld"])

    return {"A0": a0, "A1": a1, "A2": a2, "A3": a3}


def to_editor_safe_profile(source: dict[str, Any], *, keep_bookworld: bool = True) -> dict[str, Any]:
    """Conservative profile for StandarReader 2.56.1 save stability."""
    base = copy.deepcopy(source)
    base["weight"] = _normalize_weight_to_str(base.get("weight"))

    base.pop("httpHeaders", None)

    for key in CORE_ACTIONS:
        act = base.get(key)
        if not isinstance(act, dict):
            continue
        act.pop("host", None)
        act["validConfig"] = ""
        act.pop("moreKeys", None)

    if keep_bookworld:
        bw = base.get("bookWorld")
        if isinstance(bw, dict):
            bw = normalize_bookworld_requestfilters_to_string(bw)
            for _, act in bw.items():
                if not isinstance(act, dict):
                    continue
                act.pop("host", None)
                act["validConfig"] = ""
                mk = act.get("moreKeys")
                if isinstance(mk, dict):
                    rf = _request_filters_to_str(mk.get("requestFilters"))
                    act["moreKeys"] = {"requestFilters": rf} if rf else {}
                else:
                    act["moreKeys"] = {}
            base["bookWorld"] = bw
    else:
        base.pop("bookWorld", None)

    return base


def check_editor_risks(source: dict[str, Any], *, mode: str) -> list[Risk]:
    risks: list[Risk] = []

    if mode == "new":
        risks.append(Risk("medium", "NEW_SCHEMA_WRAPPER", "<top>", "使用新 schema wrapper（sourceName/sourceUrl），请执行编辑页保存回归验证"))

    hh = source.get("httpHeaders")
    if isinstance(hh, dict):
        risks.append(Risk("medium", "TOP_HTTPHEADERS", "httpHeaders", "顶层 httpHeaders 是对象，属于已知保存崩溃嫌疑字段簇"))

    w = source.get("weight")
    if not isinstance(w, str):
        risks.append(Risk("high", "WEIGHT_NON_STRING", "weight", "weight 不是字符串，2.56.1 编辑保存存在高风险（可能触发 NSNumber length 崩溃）"))
    else:
        ws = w.strip()
        if not ws:
            risks.append(Risk("high", "WEIGHT_EMPTY", "weight", "weight 为空字符串，建议使用 \"9999\""))
        else:
            try:
                iv = int(ws)
                if iv <= 0:
                    risks.append(Risk("high", "WEIGHT_NON_POSITIVE", "weight", "weight 必须是正整数的字符串"))
            except Exception:
                risks.append(Risk("high", "WEIGHT_NOT_INT_STRING", "weight", "weight 必须是整数字符串，例如 \"9999\""))

    bw = source.get("bookWorld")
    if isinstance(bw, dict):
        for bname, act in bw.items():
            if not isinstance(act, dict):
                continue
            mk = act.get("moreKeys")
            if isinstance(mk, dict) and "requestFilters" in mk and not isinstance(mk["requestFilters"], str):
                risks.append(Risk("high", "REQUESTFILTERS_NON_STRING", f"bookWorld.{bname}.moreKeys.requestFilters", "requestFilters 非字符串，编辑页保存高风险"))

    for action in CORE_ACTIONS + ["bookWorld"]:
        obj = source.get(action)
        if action == "bookWorld" and isinstance(obj, dict):
            for bname, act in obj.items():
                if not isinstance(act, dict):
                    continue
                vc = act.get("validConfig")
                if isinstance(vc, str) and vc.strip().startswith(("{", "[")):
                    risks.append(Risk("medium", "VALIDCONFIG_JSON_STRING", f"bookWorld.{bname}.validConfig", "validConfig 为 JSON 字符串，建议降级为空字符串"))
                mk = act.get("moreKeys")
                if isinstance(mk, dict) and "removeHtmlKeys" in mk:
                    risks.append(Risk("low", "REMOVEHTMLKEYS_PRESENT", f"bookWorld.{bname}.moreKeys.removeHtmlKeys", "removeHtmlKeys 存在，建议放入 A/B 末级验证"))
            continue

        if not isinstance(obj, dict):
            continue

        vc = obj.get("validConfig")
        if isinstance(vc, str) and vc.strip().startswith(("{", "[")):
            risks.append(Risk("medium", "VALIDCONFIG_JSON_STRING", f"{action}.validConfig", "validConfig 为 JSON 字符串，建议降级为空字符串"))

        mk = obj.get("moreKeys")
        if isinstance(mk, dict) and "removeHtmlKeys" in mk:
            risks.append(Risk("low", "REMOVEHTMLKEYS_PRESENT", f"{action}.moreKeys.removeHtmlKeys", "removeHtmlKeys 存在，建议放入 A/B 末级验证"))

    return risks
