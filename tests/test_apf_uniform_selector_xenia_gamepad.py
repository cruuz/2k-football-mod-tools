#!/usr/bin/env python3
"""Unit tests for the bounded APF Xenia replay controller."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import apf_uniform_selector_xenia_gamepad as gamepad  # noqa: E402


class APFUniformSelectorXeniaGamepadTests(unittest.TestCase):
    def test_frozen_replay_commands_parse(self) -> None:
        commands = [
            "TAP START 5.00",
            "TAP A 0.50",
            "TAP A 0.50",
            "TAP A 0.50",
            "TAP START 0.50",
            "TAP A 0.50",
            "TAP START 0.50",
            "TAP START 0.50",
            "TAP RT 0.35",
        ]
        parsed = [gamepad.parse_command(command) for command in commands]
        self.assertEqual([tap.control for tap in parsed], [
            "START", "A", "A", "A", "START", "A", "START", "START", "RT"
        ])

    def test_command_language_is_fail_closed(self) -> None:
        for command in (
            "TAP B 0.50",
            "TAP A",
            "HOLD A 1.00",
            "TAP RT nan",
            "TAP START 5.01",
            "TAP A 0.00",
        ):
            with self.subTest(command=command):
                with self.assertRaises(ValueError):
                    gamepad.parse_command(command)

    def test_quit_is_not_an_input_event(self) -> None:
        self.assertIsNone(gamepad.parse_command("QUIT"))
        self.assertIsNone(gamepad.parse_command("exit"))


if __name__ == "__main__":
    unittest.main()
