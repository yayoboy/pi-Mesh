import pytest

from gui.theme.palettes import PALETTES, get_palette, _REQUIRED_KEYS
from gui.theme.qss import build_qss


# --- palettes ---------------------------------------------------------------

def test_three_standard_palettes_present():
    assert set(PALETTES.keys()) == {"dark", "light", "hc"}


@pytest.mark.parametrize("name", ["dark", "light", "hc"])
def test_standard_palette_has_all_required_keys(name):
    palette = PALETTES[name]
    for key in _REQUIRED_KEYS:
        assert key in palette, f"palette {name!r} missing {key!r}"
        assert palette[key].startswith("#")
        assert len(palette[key]) in (4, 7, 9)  # #rgb, #rrggbb, #rrggbbaa


def test_get_palette_returns_dark_by_default_name():
    p = get_palette("dark")
    assert p["bg"] == "#060810"
    assert p["accent"] == "#4a9eff"


def test_get_palette_unknown_name_raises_keyerror():
    with pytest.raises(KeyError):
        get_palette("nonexistent")


def test_get_palette_custom_requires_dict():
    with pytest.raises(ValueError):
        get_palette("custom")


def test_get_palette_custom_validates_required_keys():
    incomplete = {"bg": "#000"}
    with pytest.raises(ValueError):
        get_palette("custom", custom=incomplete)


def test_get_palette_custom_returns_dict_when_complete():
    custom = {k: "#123456" for k in _REQUIRED_KEYS}
    custom["accent"] = "#ff00ff"
    p = get_palette("custom", custom=custom)
    assert p["accent"] == "#ff00ff"


# --- qss build --------------------------------------------------------------

@pytest.mark.parametrize("name", ["dark", "light", "hc"])
def test_build_qss_produces_string_with_all_colors_substituted(name):
    qss = build_qss(PALETTES[name])
    assert isinstance(qss, str)
    assert qss
    # No unresolved template placeholders (e.g. "{accent}", "{bg}", ...)
    for key in _REQUIRED_KEYS:
        assert "{" + key + "}" not in qss, f"placeholder {{{key}}} not substituted"
    # All palette colors must appear at least once in the output
    for key, value in PALETTES[name].items():
        assert value in qss, f"color {key}={value!r} not used in QSS for {name!r}"


def test_build_qss_missing_key_raises():
    incomplete = {k: "#000000" for k in _REQUIRED_KEYS if k != "accent"}
    with pytest.raises(KeyError):
        build_qss(incomplete)


def test_build_qss_uses_role_property_selectors():
    qss = build_qss(PALETTES["dark"])
    # widgets with role="muted"/"ok"/"warn"/"danger" should be styled
    for role in ("muted", "ok", "warn", "danger"):
        assert f'QLabel[role="{role}"]' in qss


def test_build_qss_dark_and_light_differ():
    a = build_qss(PALETTES["dark"])
    b = build_qss(PALETTES["light"])
    assert a != b
