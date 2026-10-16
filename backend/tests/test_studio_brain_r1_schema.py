"""R1-F reports unsupported Claude schema shapes at their schema positions."""
from copy import deepcopy

import pytest

from studio.brain_schema import UnsupportedSchema, schema_errors, to_claude_schema
from studio.brain_tasks import TASKS


@pytest.mark.parametrize("extra", [{}, {"type": "string"}, {"anyOf": [{"type": "string"}, {"type": "number"}]}])
def test_schema_valued_additional_properties_has_explicit_location(extra):
    schema = {"type": "object", "properties": {"a/b~c": {"type": "object", "additionalProperties": extra}}}
    original = deepcopy(schema)
    with pytest.raises(UnsupportedSchema) as error:
        to_claude_schema(schema)
    assert isinstance(error.value, ValueError)
    assert error.value.path == "#/properties/a~1b~0c/additionalProperties"
    assert error.value.path in str(error.value)
    assert "additionalProperties" in str(error.value)
    assert schema == original


@pytest.mark.parametrize("value", [None, True, 4, [], ["email"], {"type": "email"}])
def test_non_string_format_is_rejected_before_membership_check(value):
    schema = {"type": "array", "items": {"type": "string", "format": value}}
    with pytest.raises(UnsupportedSchema) as error:
        to_claude_schema(schema)
    assert error.value.path == "#/items/format"
    assert "format" in str(error.value)


def test_recursive_reference_and_python_cycle_report_the_offending_location():
    with pytest.raises(UnsupportedSchema) as error:
        to_claude_schema({"type": "object", "properties": {"child": {"$ref": "#"}}})
    assert error.value.path == "#/properties/child/$ref"
    assert "递归" in str(error.value)
    cyclic = {"type": "object", "properties": {}}
    cyclic["properties"]["self"] = cyclic
    with pytest.raises(UnsupportedSchema) as error:
        to_claude_schema(cyclic)
    assert error.value.path == "#/properties/self"
    for keyword in ("$recursiveRef", "$dynamicRef"):
        with pytest.raises(UnsupportedSchema) as error:
            to_claude_schema({"type": "array", "items": {keyword: "#"}})
        assert error.value.path == "#/items/" + keyword


def test_indirect_ref_cycle_is_explicit_but_nonrecursive_refs_remain_supported():
    with pytest.raises(UnsupportedSchema, match="递归") as error:
        to_claude_schema({"$defs": {"a": {"$ref": "#/$defs/b"}, "b": {"$ref": "#/$defs/a"}}, "$ref": "#/$defs/a"})
    assert "$ref" in error.value.path
    converted = to_claude_schema({"$defs": {"a": {"type": "object"}}, "items": {"$ref": "#/$defs/a"}, "type": "array"})
    assert converted["$defs"]["a"]["additionalProperties"] is False


def test_business_names_and_examples_are_data_and_full_local_validator_is_preserved():
    schema = {"type": "object", "properties": {
        "format": {"type": "string", "format": "email"},
        "additionalProperties": {"type": "string"},
        "minimum": {"type": "integer", "minimum": 1}},
        "examples": [{"format": [], "additionalProperties": {"type": "string"}}]}
    converted = to_claude_schema(schema)
    assert set(converted["properties"]) == {"format", "additionalProperties", "minimum"}
    assert converted["examples"] == schema["examples"]
    assert schema_errors({"extra": 1}, {"type": "object", "additionalProperties": {"type": "string"}})
    assert not schema_errors({"extra": "yes"}, {"type": "object", "additionalProperties": {"type": "string"}})


@pytest.mark.parametrize("task", list(TASKS))
def test_all_existing_task_schemas_convert_without_mutation(task):
    schema = TASKS[task].schema
    snapshot = deepcopy(schema)
    assert to_claude_schema(schema)["additionalProperties"] is False
    assert schema == snapshot
