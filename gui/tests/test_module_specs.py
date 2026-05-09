import pytest

from gui.pages._module_specs import ALL_MODULE_SPECS, Field, ModuleSpec


def test_all_specs_have_distinct_titles():
    titles = [s.title for s in ALL_MODULE_SPECS]
    assert len(titles) == len(set(titles))


def test_all_specs_have_distinct_getters_and_setters():
    getters = [s.getter for s in ALL_MODULE_SPECS]
    setters = [s.setter for s in ALL_MODULE_SPECS]
    assert len(getters) == len(set(getters))
    assert len(setters) == len(set(setters))


def test_every_field_has_known_kind():
    for spec in ALL_MODULE_SPECS:
        for field in spec.fields:
            assert field.kind in ("bool", "int", "str", "enum"), \
                f"{spec.title}.{field.key}: bad kind {field.kind!r}"


def test_int_fields_have_valid_range():
    for spec in ALL_MODULE_SPECS:
        for field in spec.fields:
            if field.kind != "int":
                continue
            if field.extra is None:
                continue
            lo, hi = field.extra
            assert lo <= hi, f"{spec.title}.{field.key}: lo > hi"


def test_enum_fields_have_choices():
    for spec in ALL_MODULE_SPECS:
        for field in spec.fields:
            if field.kind != "enum":
                continue
            assert isinstance(field.extra, list) and len(field.extra) > 0


def test_field_keys_unique_within_a_spec():
    for spec in ALL_MODULE_SPECS:
        keys = [f.key for f in spec.fields]
        assert len(keys) == len(set(keys)), f"{spec.title} has duplicate keys"


def test_default_value_type_matches_kind():
    for spec in ALL_MODULE_SPECS:
        for field in spec.fields:
            d = field.default
            if d is None:
                continue
            if field.kind == "bool":
                assert isinstance(d, bool)
            elif field.kind == "int":
                assert isinstance(d, int)
            elif field.kind == "str":
                assert isinstance(d, str)
            elif field.kind == "enum":
                assert isinstance(d, str)
                assert d in (field.extra or [])


def test_getters_match_meshtasticd_client_naming():
    """Every getter should follow the get_<x>_config / get_<x>_module_config naming."""
    for spec in ALL_MODULE_SPECS:
        assert spec.getter.startswith("get_"), spec.getter
        assert spec.setter.startswith("set_"), spec.setter
        # getter and setter share the same suffix
        assert spec.getter[4:] == spec.setter[4:], f"mismatch: {spec.getter} vs {spec.setter}"


def test_we_have_all_nine_modules():
    expected = {
        "Telemetry module",
        "Canned messages",
        "Range test",
        "Neighbor info",
        "Store and forward",
        "External notification",
        "Ambient lighting",
        "Detection sensor",
        "Serial module",
    }
    assert {s.title for s in ALL_MODULE_SPECS} == expected
