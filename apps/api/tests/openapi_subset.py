"""vendored OpenAPI 부분 검증기 — Map 계약 게이트(transport·weather)가 함께 쓴다.

저장소에 `jsonschema`가 없어 fixture가 쓰는 구성(`$ref`·`anyOf`·`type`·`required`·`additionalProperties`
(`false`·schema)·`enum`·`const`·`items`)만 다룬다. 각 게이트는 이 검증기가 실제로 빨개지는지 따로 확인한다(항진명제 방지).
"""

from __future__ import annotations

from typing import Any


def json_types(root: dict[str, Any], schema: dict[str, Any]) -> set[str]:
    """schema가 허용하는 JSON 타입 집합. `$ref`는 object, `integer`는 `number`에 포함된다고 본다."""
    if "$ref" in schema:
        return {"object"}
    if "anyOf" in schema:
        out: set[str] = set()
        for branch in schema["anyOf"]:
            out |= json_types(root, branch)
        return out
    if "const" in schema:
        return {type(schema["const"]).__name__.replace("str", "string")}
    kind = schema.get("type")
    if kind is None:
        return {"string", "number", "integer", "boolean", "object", "array", "null"}
    return {"integer", "number"} if kind == "number" else {kind}


_TYPES: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "array": (list,),
    "object": (dict,),
    "null": (type(None),),
}


def schema_errors(spec: dict[str, Any], schema: dict[str, Any], value: Any, at: str) -> list[str]:
    if "$ref" in schema:
        name = schema["$ref"].rsplit("/", 1)[-1]
        return schema_errors(spec, spec["components"]["schemas"][name], value, at)
    if "anyOf" in schema:
        branches = [schema_errors(spec, branch, value, at) for branch in schema["anyOf"]]
        return [] if any(not b for b in branches) else [f"{at}: anyOf 불일치 {branches}"]
    if "const" in schema and value != schema["const"]:
        return [f"{at}: const {schema['const']!r} ≠ {value!r}"]
    if "enum" in schema and value not in schema["enum"]:
        return [f"{at}: enum 밖 {value!r}"]
    kind = schema.get("type")
    if kind is not None:
        allowed = _TYPES[kind]
        if isinstance(value, bool) and kind in ("integer", "number"):
            return [f"{at}: bool은 {kind}가 아니다"]
        if not isinstance(value, allowed):
            return [f"{at}: {kind} 아님 ({type(value).__name__})"]
    out: list[str] = []
    if isinstance(value, dict) and (kind == "object" or "properties" in schema):
        properties = schema.get("properties", {})
        for name in schema.get("required", []):
            if name not in value:
                out.append(f"{at}.{name}: required 누락")
        for name, item in value.items():
            if name in properties:
                out += schema_errors(spec, properties[name], item, f"{at}.{name}")
            elif schema.get("additionalProperties") is False:
                out.append(f"{at}.{name}: 선언되지 않은 필드")
            elif isinstance(schema.get("additionalProperties"), dict):
                out += schema_errors(spec, schema["additionalProperties"], item, f"{at}.{name}")
    if isinstance(value, list) and "items" in schema:
        for index, item in enumerate(value):
            out += schema_errors(spec, schema["items"], item, f"{at}[{index}]")
    return out
