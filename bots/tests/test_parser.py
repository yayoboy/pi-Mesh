import pytest

from bots.parser import parse_command


def test_simple_command_no_args():
    assert parse_command("!ping", "!") == ("ping", [])


def test_command_with_args():
    assert parse_command("!nodes !aabb 7", "!") == ("nodes", ["!aabb", "7"])


def test_command_lowercased():
    assert parse_command("!PING", "!")[0] == "ping"


def test_args_preserve_case():
    cmd, args = parse_command("!nodes !AaBb", "!")
    assert cmd == "nodes"
    assert args == ["!AaBb"]


def test_no_prefix_match_returns_none():
    assert parse_command("ping", "!") == (None, [])
    assert parse_command("hello world", "!") == (None, [])


def test_leading_whitespace_stripped():
    assert parse_command("   !ping", "!") == ("ping", [])


def test_trailing_whitespace_ignored():
    assert parse_command("!ping   ", "!") == ("ping", [])


def test_empty_command_after_prefix_returns_none():
    assert parse_command("!", "!") == (None, [])
    assert parse_command("!   ", "!") == (None, [])


def test_empty_text_returns_none():
    assert parse_command("", "!") == (None, [])


def test_empty_prefix_returns_none():
    assert parse_command("ping", "") == (None, [])


def test_none_prefix_returns_none():
    assert parse_command("ping", None) == (None, [])


def test_multi_char_prefix():
    assert parse_command("!!ping", "!!") == ("ping", [])
    assert parse_command("!ping", "!!") == (None, [])


def test_prefix_is_full_word():
    assert parse_command("@bot ping", "@bot") == ("ping", [])
    assert parse_command("@bot ping arg1 arg2", "@bot") == ("ping", ["arg1", "arg2"])


def test_internal_extra_whitespace_collapses():
    cmd, args = parse_command("!nodes    foo     bar", "!")
    assert cmd == "nodes"
    assert args == ["foo", "bar"]
