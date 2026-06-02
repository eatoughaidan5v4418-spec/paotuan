"""Small YAML compatibility layer for project-local runtime files.

PyYAML is used when available. The fallback parser intentionally supports only
the subset used by this project's YAML files: indentation-based mappings,
lists, quoted/scalar strings, booleans, numbers, nulls, inline lists, and
simple literal/folded block scalars.
"""

from __future__ import annotations

import ast
import re
from typing import Any


try:  # pragma: no cover - exercised only when PyYAML is installed
    import yaml as _pyyaml
except ModuleNotFoundError:  # pragma: no cover - fallback is covered instead
    _pyyaml = None


class YAMLError(Exception):
    """Fallback YAML parse error."""


def safe_load(text: str) -> Any:
    if _pyyaml is not None:
        return _pyyaml.safe_load(text)
    return _FallbackParser(text).parse()


def _strip_comment(line: str) -> str:
    in_single = False
    in_double = False
    for index, char in enumerate(line):
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif char == "#" and not in_single and not in_double:
            return line[:index].rstrip()
    return line.rstrip()


def _split_key_value(text: str) -> tuple[str, str | None]:
    in_single = False
    in_double = False
    for index, char in enumerate(text):
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif char == ":" and not in_single and not in_double:
            return text[:index].strip(), text[index + 1 :].strip()
    return text.strip(), None


def _parse_scalar(value: str) -> Any:
    text = value.strip()
    if text == "":
        return ""
    lower = text.lower()
    if lower in {"true", "false"}:
        return lower == "true"
    if lower in {"null", "none", "~"}:
        return None
    if text.startswith(('"', "'")) and text.endswith(text[0]):
        try:
            return ast.literal_eval(text)
        except (SyntaxError, ValueError):
            return text[1:-1]
    if text.startswith("[") and text.endswith("]"):
        try:
            return ast.literal_eval(text)
        except (SyntaxError, ValueError):
            inner = text[1:-1].strip()
            if not inner:
                return []
            return [_parse_scalar(part) for part in re.split(r"\s*,\s*", inner)]
    if re.fullmatch(r"[-+]?\d+", text):
        try:
            return int(text)
        except ValueError:
            return text
    if re.fullmatch(r"[-+]?\d+\.\d+", text):
        try:
            return float(text)
        except ValueError:
            return text
    return text


class _FallbackParser:
    def __init__(self, text: str) -> None:
        self.lines: list[tuple[int, str]] = []
        for raw in text.splitlines():
            raw = raw.lstrip("\ufeff")
            if not raw.strip() or raw.lstrip().startswith("---"):
                continue
            cleaned = _strip_comment(raw)
            if not cleaned.strip():
                continue
            indent = len(cleaned) - len(cleaned.lstrip(" "))
            self.lines.append((indent, cleaned.strip()))
        self.index = 0

    def parse(self) -> Any:
        if not self.lines:
            return {}
        return self._parse_block(self.lines[0][0])

    def _parse_block(self, indent: int) -> Any:
        if self.index >= len(self.lines):
            return {}
        _, content = self.lines[self.index]
        if content.startswith("- "):
            return self._parse_list(indent)
        return self._parse_mapping(indent)

    def _parse_mapping(self, indent: int) -> dict[str, Any]:
        result: dict[str, Any] = {}
        while self.index < len(self.lines):
            line_indent, content = self.lines[self.index]
            if line_indent < indent:
                break
            if line_indent > indent:
                raise YAMLError(f"unexpected indent near: {content}")
            if content.startswith("- "):
                break
            key, value = _split_key_value(content)
            if not key or value is None:
                raise YAMLError(f"invalid mapping line: {content}")
            self.index += 1
            if value in {"|", ">"}:
                result[key] = self._parse_block_scalar(indent, value)
                continue
            if value == "":
                if self.index < len(self.lines):
                    next_indent, next_content = self.lines[self.index]
                    if next_content.startswith("- ") and next_indent >= indent:
                        result[key] = self._parse_list(next_indent)
                    elif next_indent > indent:
                        result[key] = self._parse_block(next_indent)
                    else:
                        result[key] = None
                else:
                    result[key] = None
            else:
                result[key] = self._parse_plain_value(value, indent)
        return result

    def _parse_list(self, indent: int) -> list[Any]:
        result: list[Any] = []
        while self.index < len(self.lines):
            line_indent, content = self.lines[self.index]
            if line_indent < indent:
                break
            if line_indent > indent:
                raise YAMLError(f"unexpected indent near: {content}")
            if not content.startswith("- "):
                break
            item_text = content[2:].strip()
            self.index += 1
            if item_text == "":
                item: Any
                if self.index < len(self.lines) and self.lines[self.index][0] > indent:
                    item = self._parse_block(self.lines[self.index][0])
                else:
                    item = None
                result.append(item)
                continue

            key, value = _split_key_value(item_text)
            if value is not None and key:
                if value in {"|", ">"}:
                    item_value = self._parse_block_scalar(line_indent, value)
                else:
                    item_value = self._parse_plain_value(value, line_indent) if value else None
                item_dict: dict[str, Any] = {key: item_value}
                if self.index < len(self.lines) and self.lines[self.index][0] > indent:
                    nested = self._parse_mapping(self.lines[self.index][0])
                    item_dict.update(nested)
                result.append(item_dict)
            else:
                result.append(_parse_scalar(item_text))
        return result

    def _parse_plain_value(self, value: str, parent_indent: int) -> Any:
        parsed = _parse_scalar(value)
        if not isinstance(parsed, str):
            return parsed
        continuations: list[str] = []
        while self.index < len(self.lines):
            line_indent, content = self.lines[self.index]
            if line_indent <= parent_indent or content.startswith("- "):
                break
            _, nested_value = _split_key_value(content)
            if nested_value is not None:
                break
            continuations.append(content)
            self.index += 1
        if continuations:
            return " ".join([parsed, *continuations])
        return parsed

    def _parse_block_scalar(self, parent_indent: int, style: str) -> str:
        parts: list[str] = []
        while self.index < len(self.lines):
            line_indent, content = self.lines[self.index]
            if line_indent <= parent_indent:
                break
            parts.append(content)
            self.index += 1
        if style == ">":
            return " ".join(parts).strip() + ("\n" if parts else "")
        return "\n".join(parts) + ("\n" if parts else "")
