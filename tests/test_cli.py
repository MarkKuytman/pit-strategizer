"""Smoke tests for the ``pit-strategizer`` command-line entry point."""

from __future__ import annotations

import pytest

from pit_strategizer.cli import build_parser, main


def test_help_lists_the_program(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["--help"])

    assert exit_info.value.code == 0
    assert "pit-strategizer" in capsys.readouterr().out


def test_bare_invocation_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    assert "pit-strategizer" in capsys.readouterr().out


def test_parser_is_named_for_the_entry_point() -> None:
    assert build_parser().prog == "pit-strategizer"
