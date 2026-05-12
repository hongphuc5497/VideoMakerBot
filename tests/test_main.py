import os
from unittest.mock import patch

import main


def test_clear_screen_skips_clear_without_term(monkeypatch):
    monkeypatch.delenv("TERM", raising=False)
    monkeypatch.setattr(main, "name", "posix")

    with patch("main.subprocess.run") as run:
        main.clear_screen()

    run.assert_not_called()


def test_clear_screen_runs_when_term_is_set(monkeypatch):
    monkeypatch.setenv("TERM", "xterm")
    monkeypatch.setattr(main, "name", "posix")

    with patch("main.subprocess.run") as run:
        main.clear_screen()

    run.assert_called_once_with(["clear"], shell=False)


def test_clear_screen_runs_windows_command(monkeypatch):
    monkeypatch.delenv("TERM", raising=False)
    monkeypatch.setattr(main, "name", "nt")

    with patch("main.subprocess.run") as run:
        main.clear_screen()

    run.assert_called_once_with(["cls"], shell=True)
