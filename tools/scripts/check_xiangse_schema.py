#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


REQUIRED_TOP_FIELDS = [
    "sourceName",
    "sourceUrl",
    "sourceType",
    "enable",
    "weight",
]

ACTION_KEYS = ["searchBook", "bookDetail", "chapterList", "chapterContent"]
REQUIRED_ACTION_FIELDS = ["actionID", "parserID", "requestInfo", "responseFormatType"]

FORBIDDEN_TOP_KEYS = {
    "bookSourceName",
    "bookSourceUrl",
    "bookSourceGroup",
    "httpUserAgent",
}

BAD_REQUESTINFO_PATTERNS = [
    (re.compile(r"\bjava\.getParams\s*\(", re.I), "requestInfo 使用了 java.getParams()（非香色运行时）"),
]

WARN_REQUESTINFO_PATTERNS = [
    (re.compile(r"\bmethod\s*:", re.I), "requestInfo 使用 method: 键，香色应使用 POST"),
    (re.compile(r"\bdata\s*:", re.I), "requestInfo 使用 data: 键，香色应使用 httpParams"),
    (re.compile(r"\bheaders\s*:", re.I), "requestInfo 使用 headers: 键，香色应使用 httpHeaders"),
]

ALLOWED_RESPONSE_FORMAT_TYPES = {
    "",
    "html",
    "xml",
    "json",
    "base64str",
    "data",
}

ALLOWED_RESPONSE_DECRYPT_TYPES = {
    "",
    "encryptType1",
}


def _is_int_not_bool(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _is_int_string(v: Any) -> bool:
    return isinstance(v, str) and bool(re.fullmatch(r"-?\d+", v))


def _warn_or_error(
    errors: list[str],
    warnings: list[str],
    *,
    strict: bool,
    msg: str,
) -> None:
    if strict:
        errors.append(msg)
    else:
        warnings.append(msg)


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _iter_sources(doc: Any) -> list[tuple[str, dict[str, Any]]]:
    if not isinstance(doc, dict):
        return []
    top_keys = set(doc.keys())
    if (
        top_keys.intersection(REQUIRED_TOP_FIELDS)
        or top_keys.intersection(FORBIDDEN_TOP_KEYS)
        or top_keys.intersection(ACTION_KEYS)
    ):
        # A single source object without alias wrapper.
        return [("<root>", doc)]

    pairs: list[tuple[str, dict[str, Any]]] = []
    for k, v in doc.items():
        if not isinstance(v, dict):
            continue
        vk = set(v.keys())
        if (
            vk.intersection(REQUIRED_TOP_FIELDS)
            or vk.intersection(FORBIDDEN_TOP_KEYS)
            or vk.intersection(ACTION_KEYS)
        ):
            pairs.append((k, v))
    return pairs


def _check_one_source(
    name: str,
    src: dict[str, Any],
    errors: list[str],
    warnings: list[str],
    *,
    strict_requestinfo: bool,
) -> None:
    for bad in FORBIDDEN_TOP_KEYS:
        if bad in src:
            errors.append(f"[{name}] 命中非香色顶层字段: {bad}")

    for req in REQUIRED_TOP_FIELDS:
        if req not in src:
            errors.append(f"[{name}] 缺少顶层必需字段: {req}")

    st = src.get("sourceType")
    if st is not None and st != "text":
        warnings.append(f"[{name}] sourceType={st}（当前流程默认 text 书源）")

    if "weight" in src and not isinstance(src.get("weight"), str):
        warnings.append(
            f"[{name}] weight 类型为 {type(src.get('weight')).__name__}，建议归一化为整数字符串"
        )
    elif "weight" in src and isinstance(src.get("weight"), str):
        w = src.get("weight")
        if not _is_int_string(w):
            warnings.append(f"[{name}] weight={w!r} 不是整数字符串，建议归一化")

    if "enable" in src and not _is_int_not_bool(src.get("enable")):
        warnings.append(
            f"[{name}] enable 类型为 {type(src.get('enable')).__name__}，建议归一化为 1/0 整型"
        )

    for action in ACTION_KEYS:
        obj = src.get(action)
        if obj is None:
            errors.append(f"[{name}] 缺少动作: {action}")
            continue
        if not isinstance(obj, dict):
            errors.append(f"[{name}] 动作 {action} 不是对象")
            continue
        for req in REQUIRED_ACTION_FIELDS:
            if req not in obj:
                errors.append(f"[{name}] 动作 {action} 缺少字段: {req}")

        rft = obj.get("responseFormatType")
        if isinstance(rft, str):
            if rft not in ALLOWED_RESPONSE_FORMAT_TYPES:
                errors.append(
                    f"[{name}] 动作 {action} responseFormatType={rft!r} 不在白名单"
                )
        else:
            errors.append(
                f"[{name}] 动作 {action} responseFormatType 类型非法: {type(rft).__name__}"
            )

        if "responseDecryptType" in obj:
            rdt = obj.get("responseDecryptType")
            if not isinstance(rdt, str):
                errors.append(
                    f"[{name}] 动作 {action} responseDecryptType 类型非法: {type(rdt).__name__}"
                )
            elif rdt not in ALLOWED_RESPONSE_DECRYPT_TYPES:
                errors.append(
                    f"[{name}] 动作 {action} responseDecryptType={rdt!r} 不在白名单"
                )

        req_info = obj.get("requestInfo")
        if isinstance(req_info, str):
            for pat, msg in BAD_REQUESTINFO_PATTERNS:
                if pat.search(req_info):
                    errors.append(f"[{name}] 动作 {action}: {msg}")
            for pat, msg in WARN_REQUESTINFO_PATTERNS:
                if pat.search(req_info):
                    _warn_or_error(
                        errors,
                        warnings,
                        strict=strict_requestinfo,
                        msg=f"[{name}] 动作 {action}: {msg}",
                    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Check whether a source JSON matches xiangse schema.")
    parser.add_argument("input", help="Path to source JSON")
    parser.add_argument(
        "--strict-requestinfo",
        action="store_true",
        help="Treat method:/data:/headers: in requestInfo as errors (default warns only).",
    )
    args = parser.parse_args()

    path = Path(args.input).expanduser().resolve()
    if not path.exists():
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        return 2

    try:
        doc = _load_json(path)
    except Exception as exc:
        print(f"ERROR: invalid JSON: {exc}", file=sys.stderr)
        return 2

    errors: list[str] = []
    warnings: list[str] = []
    sources = _iter_sources(doc)
    if not sources:
        errors.append("顶层必须是对象，且至少包含一个 sourceName->sourceConfig 映射。")
    else:
        for name, src in sources:
            _check_one_source(
                name,
                src,
                errors,
                warnings,
                strict_requestinfo=args.strict_requestinfo,
            )

    if warnings:
        print("WARNINGS:")
        for w in warnings:
            print(f"- {w}")

    if errors:
        print("SCHEMA_CHECK: FAIL")
        for e in errors:
            print(f"- {e}")
        print(f"ERROR_COUNT: {len(errors)}")
        print(f"WARNING_COUNT: {len(warnings)}")
        print(f"SOURCE_COUNT: {len(sources)}")
        return 1

    print("SCHEMA_CHECK: PASS")
    print(f"ERROR_COUNT: {len(errors)}")
    print(f"WARNING_COUNT: {len(warnings)}")
    print(f"SOURCE_COUNT: {len(sources)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
