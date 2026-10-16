"""结构化输出的 schema 转换及不依赖第三方包的本地完整校验。"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, time
from decimal import Decimal
import ipaddress
import json
import math
import re
from urllib.parse import urlsplit
import uuid


_MAP_SCHEMAS = {"properties", "patternProperties", "$defs", "definitions", "dependentSchemas"}
_ONE_SCHEMA = {"items", "additionalItems", "additionalProperties", "unevaluatedProperties",
               "unevaluatedItems", "contains", "propertyNames", "not", "if", "then", "else", "contentSchema"}
_MANY_SCHEMAS = {"prefixItems", "allOf", "anyOf", "oneOf"}
_REMOVED = {"minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf",
            "minLength", "maxLength", "pattern", "maxItems", "uniqueItems"}
_FORMATS = {"date-time", "time", "date", "duration", "email", "hostname", "uri", "ipv4", "ipv6", "uuid"}


class UnsupportedSchema(ValueError):
    """An unsupported schema shape, with its JSON Pointer location."""

    def __init__(self, reason: str, path: str = "#"):
        self.path = self.position = path
        super().__init__(f"{path}: {reason}")


def _pointer(path: str, key) -> str:
    return path + "/" + str(key).replace("~", "~0").replace("/", "~1")


def _children_with_paths(node: dict, path: str):
    for key, value in node.items():
        location = _pointer(path, key)
        if key in _MAP_SCHEMAS and isinstance(value, dict):
            yield from ((child, _pointer(location, name)) for name, child in value.items())
        elif key in _ONE_SCHEMA:
            if isinstance(value, list):
                yield from ((child, _pointer(location, index)) for index, child in enumerate(value))
            else:
                yield value, location
        elif key in _MANY_SCHEMAS and isinstance(value, list):
            yield from ((child, _pointer(location, index)) for index, child in enumerate(value))
        elif key == "dependencies" and isinstance(value, dict):
            yield from ((child, _pointer(location, name)) for name, child in value.items()
                        if isinstance(child, (dict, bool)))


def _children(node: dict):
    yield from (child for child, _ in _children_with_paths(node, "#"))


def _reference(root: dict, reference: str, path: str = "#/$ref"):
    if not isinstance(reference, str) or (reference != "#" and not reference.startswith("#/")):
        raise UnsupportedSchema("导演 schema 只允许本地引用", path)
    value = root
    for part in reference[2:].split("/") if reference != "#" else []:
        part = part.replace("~1", "/").replace("~0", "~")
        try:
            value = value[int(part)] if isinstance(value, list) else value[part]
        except (KeyError, TypeError, ValueError, IndexError):
            raise UnsupportedSchema("导演 schema 引用不存在", path) from None
    if not isinstance(value, (dict, bool)):
        raise UnsupportedSchema("导演 schema 引用不是 schema", path)
    return value


def _assert_nonrecursive(schema: dict) -> None:
    visiting, visited = set(), set()

    def visit(node, path):
        if isinstance(node, bool):
            return
        if not isinstance(node, dict):
            raise UnsupportedSchema("导演 schema 节点格式不正确", path)
        identity = id(node)
        if identity in visiting:
            raise UnsupportedSchema("导演 schema 不允许递归", path)
        if identity in visited:
            return
        visiting.add(identity)
        if "$ref" in node:
            reference_path = _pointer(path, "$ref")
            visit(_reference(schema, node["$ref"], reference_path), reference_path)
        for keyword in ("$dynamicRef", "$recursiveRef"):
            if keyword in node:
                raise UnsupportedSchema("导演 schema 不允许动态或递归引用", _pointer(path, keyword))
        for child, location in _children_with_paths(node, path):
            visit(child, location)
        visiting.remove(identity)
        visited.add(identity)

    visit(schema, "#")


def _assert_claude_supported(schema: dict) -> None:
    def visit(node, path):
        if not isinstance(node, dict):
            return
        if "additionalProperties" in node and not isinstance(node["additionalProperties"], bool):
            raise UnsupportedSchema("Claude 不支持 additionalProperties schema，必须为布尔值",
                                    _pointer(path, "additionalProperties"))
        if "format" in node and not isinstance(node["format"], str):
            raise UnsupportedSchema("format 必须为字符串", _pointer(path, "format"))
        for child, location in _children_with_paths(node, path):
            visit(child, location)

    visit(schema, "#")


def to_claude_schema(schema: dict) -> dict:
    """只遍历 schema 位置，业务字段名及 examples/default 数据不参与转换。"""
    _assert_nonrecursive(schema)
    _assert_claude_supported(schema)
    result = deepcopy(schema)

    def visit(node):
        if not isinstance(node, dict):
            return
        removed = []
        for key in list(node):
            remove = key in _REMOVED or (key == "minItems" and node[key] > 1)
            remove = remove or (key == "format" and node[key] not in _FORMATS)
            if remove:
                value = json.dumps(node.pop(key), ensure_ascii=False, allow_nan=False)
                removed.append(f"约束：{key}={value}")
        if removed:
            node["description"] = "；".join(([node["description"]] if node.get("description") else []) + removed)
        kinds = node.get("type", [])
        if kinds == "object" or (isinstance(kinds, list) and "object" in kinds) or "properties" in node:
            node["additionalProperties"] = False
        for child in _children(node):
            visit(child)

    visit(result)
    return result


def _valid_format(value: str, kind: str) -> bool:
    try:
        if kind == "date-time":
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return "T" in value.upper() and parsed.tzinfo is not None
        if kind == "date":
            date.fromisoformat(value)
        elif kind == "time":
            time.fromisoformat(value.replace("Z", "+00:00"))
        elif kind == "uuid":
            uuid.UUID(value)
        elif kind in {"ipv4", "ipv6"}:
            return ipaddress.ip_address(value).version == (4 if kind == "ipv4" else 6)
        elif kind == "email":
            return re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value) is not None
        elif kind == "hostname":
            return len(value) <= 253 and all(re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label)
                                             for label in value.removesuffix(".").split("."))
        elif kind == "uri":
            return bool(urlsplit(value).scheme) and not any(character.isspace() for character in value)
        elif kind == "duration":
            return re.fullmatch(r"P(?=\d|T\d)(?:\d+Y)?(?:\d+M)?(?:\d+D)?(?:T(?:\d+H)?(?:\d+M)?(?:\d+(?:\.\d+)?S)?)?", value) is not None
    except (ValueError, OverflowError):
        return False
    return True


def schema_errors(value, schema: dict) -> list[str]:
    """校验原始 schema，错误仅含路径/约束名，不能携带素材或模型输出。"""
    _assert_nonrecursive(schema)

    def check(item, node, path):
        if node is True:
            return []
        if node is False:
            return [path + " 不允许该值"]
        errors = []
        if "$ref" in node:
            errors.extend(check(item, _reference(schema, node["$ref"]), path))
        for sub in node.get("allOf", []):
            errors.extend(check(item, sub, path))
        for keyword in ("anyOf", "oneOf"):
            if keyword in node:
                count = sum(not check(item, sub, path) for sub in node[keyword])
                if (keyword == "anyOf" and count == 0) or (keyword == "oneOf" and count != 1):
                    errors.append(path + " 不符合 " + keyword)
        if "not" in node and not check(item, node["not"], path):
            errors.append(path + " 不符合 not")
        if "if" in node:
            branch = "else" if check(item, node["if"], path) else "then"
            if branch in node:
                errors.extend(check(item, node[branch], path))
        valid_types = {
            "object": isinstance(item, dict), "array": isinstance(item, list), "string": isinstance(item, str),
            "boolean": type(item) is bool, "integer": type(item) is int,
            "number": type(item) is int or (type(item) is float and math.isfinite(item)), "null": item is None,
        }
        kinds = node.get("type")
        if kinds is not None and not any(valid_types.get(kind, False) for kind in (kinds if isinstance(kinds, list) else [kinds])):
            return errors + [path + " 类型不符合约束"]
        # JSON true 和数字 1 不能混作同一个枚举值。
        def equals(candidate):
            return json.dumps(item, sort_keys=True, ensure_ascii=False) == json.dumps(candidate, sort_keys=True, ensure_ascii=False)
        if "enum" in node and not any(equals(candidate) for candidate in node["enum"]):
            errors.append(path + " 不在 enum 范围")
        if "const" in node and not equals(node["const"]):
            errors.append(path + " 不符合 const")
        if isinstance(item, dict):
            properties = node.get("properties", {})
            errors.extend(path + "." + key + " 缺少必填字段" for key in node.get("required", []) if key not in item)
            for key, child in item.items():
                matched = False
                if key in properties:
                    errors.extend(check(child, properties[key], path + "." + key))
                    matched = True
                for pattern, sub in node.get("patternProperties", {}).items():
                    if re.search(pattern, key):
                        errors.extend(check(child, sub, path + "." + key))
                        matched = True
                if not matched and "additionalProperties" in node:
                    # 未知字段名也可能来自原文，不复制到错误信息中。
                    errors.extend(check(child, node["additionalProperties"], path + ".<额外字段>"))
            for keyword, comparison in (("minProperties", len(item) < node.get("minProperties", 0)),
                                         ("maxProperties", len(item) > node.get("maxProperties", math.inf))):
                if comparison:
                    errors.append(path + " 不符合 " + keyword)
        elif isinstance(item, list):
            if len(item) < node.get("minItems", 0) or len(item) > node.get("maxItems", math.inf):
                errors.append(path + " 数量不符合约束")
            if node.get("uniqueItems") and len({json.dumps(child, sort_keys=True, ensure_ascii=False) for child in item}) != len(item):
                errors.append(path + " 不允许重复项")
            prefix = node.get("prefixItems", [])
            for index, child in enumerate(item):
                if index < len(prefix):
                    child_schema = prefix[index]
                elif isinstance(node.get("items"), list):
                    child_schema = node["items"][index] if index < len(node["items"]) else node.get("additionalItems", True)
                else:
                    child_schema = node.get("items", True)
                errors.extend(check(child, child_schema, f"{path}[{index}]"))
        elif isinstance(item, str):
            if len(item) < node.get("minLength", 0) or len(item) > node.get("maxLength", math.inf) or (node.get("minLength", 0) > 0 and not item.strip()):
                errors.append(path + " 长度不符合约束")
            if "pattern" in node and re.search(node["pattern"], item) is None:
                errors.append(path + " 不符合 pattern")
            if "format" in node and not _valid_format(item, node["format"]):
                errors.append(path + " 不符合 format")
        elif type(item) in (int, float):
            if not math.isfinite(item):
                return errors + [path + " 必须是有限数字"]
            for keyword, failed in (
                ("minimum", item < node.get("minimum", -math.inf)),
                ("maximum", item > node.get("maximum", math.inf)),
                ("exclusiveMinimum", item <= node.get("exclusiveMinimum", -math.inf)),
                ("exclusiveMaximum", item >= node.get("exclusiveMaximum", math.inf)),
            ):
                if failed:
                    errors.append(path + " 不符合 " + keyword)
            if "multipleOf" in node and Decimal(str(item)) % Decimal(str(node["multipleOf"])) != 0:
                errors.append(path + " 不符合 multipleOf")
        return errors

    return check(value, schema, "$")
