"""Portable configuration must not silently grant access to the working directory."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("configuration_server", Path(__file__).parents[1] / "server.py")
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


class ConfigurationTests(unittest.TestCase):
    def test_missing_configuration_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            project = Path(directory) / "demo.gprj"
            project.write_text("<Project />", encoding="ascii")
            with self.assertRaisesRegex(ValueError, "GOWIN_ALLOWED_ROOTS"):
                server.gowin_inspect_project(str(project))
            with self.assertRaisesRegex(ValueError, "GOWIN_HOME"):
                server.gowin_environment()

    def test_empty_and_relative_configuration_rejected(self):
        for value in ("", "   ", ".", "relative/path"):
            with self.subTest(value=value), patch.dict(os.environ, {
                "GOWIN_HOME": value, "GOWIN_ALLOWED_ROOTS": value,
            }):
                with self.assertRaises(ValueError):
                    server._gowin_home()
                with self.assertRaises(ValueError):
                    server._allowed_roots()

    def test_explicit_roots_and_installation(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            with patch.dict(os.environ, {
                "GOWIN_HOME": first,
                "GOWIN_ALLOWED_ROOTS": f" {first} ; ; {second} ",
            }):
                result = server.gowin_environment()
                self.assertEqual(result["gowin_home"], str(Path(first).resolve()))
                self.assertEqual(result["allowed_roots"], [str(Path(p).resolve()) for p in (first, second)])
                self.assertFalse(result["gw_sh_exists"])
                self.assertFalse(result["hardware_programming_exposed"])

    def test_one_relative_root_rejects_entire_configuration(self):
        with tempfile.TemporaryDirectory() as root:
            with patch.dict(os.environ, {"GOWIN_ALLOWED_ROOTS": f"{root};."}):
                with self.assertRaises(ValueError):
                    server._allowed_roots()
