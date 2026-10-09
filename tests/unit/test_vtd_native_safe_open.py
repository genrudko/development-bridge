"""Isolated tests for server-pinned native VTD OpenEx safe stencil tool."""
from __future__ import annotations

import base64
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from managed.visio import visio_managed_extension as extension


class MCPRecorder:
    def __init__(self):
        self.tools = {}

    def tool(self):
        def capture(func):
            self.tools[func.__name__] = func
            return func
        return capture


class FakeMasters:
    Count = 2

    def Item(self, number):
        return SimpleNamespace(
            Name=("Т2" if number == 1 else "Генератор"),
            NameU=("Т 2_х обмоточный" if number == 1 else "Генератор"),
        )


class FakeDocs:
    def __init__(self, raise_error=False):
        self.calls = []
        self.raise_error = raise_error

    def OpenEx(self, path, flags):
        self.calls.append((path, flags))
        if self.raise_error:
            raise RuntimeError("COM read-only file not opened")
        return SimpleNamespace(Masters=FakeMasters())


class StencilSafeOpenTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.originals = self.dir / "originals"
        self.originals.mkdir()
        self.docs = FakeDocs()
        self.mcp = MCPRecorder()
        receiver_source = (
            Path(__file__).resolve().parents[2] / "managed" / "visio"
            / "artifact_receiver.py"
        ).read_bytes()
        with patch.object(
            extension, "ARTIFACT_RECEIVER_SOURCE_B64",
            base64.b64encode(receiver_source).decode("ascii"),
        ):
            extension.install({
                "mcp": self.mcp,
                "visio": SimpleNamespace(app=SimpleNamespace(Documents=self.docs)),
                "_parse_page": lambda value: value,
                "_ok": lambda value: {"data": value},
                "_err": lambda exc: {"error": str(exc)},
                "WORKSPACE": str(self.dir / "workspace"),
                "ROOT": str(self.dir / "app"),
            })
        self.probe = self.mcp.tools["probe_original_vtd_stencil"]

    def test_safe_macro_disabled_open_preserves_both_names(self):
        path = self.originals / "Трансформаторы.vss"
        contents = bytes.fromhex("d0cf11e0a1b11ae1") + b"mock"
        path.write_bytes(contents)
        with patch.object(extension, "Path", lambda name: self.originals):
            result = self.probe("Трансформаторы.vss")
        self.assertTrue(result["data"]["opened"])
        self.assertEqual(result["data"]["count"], 2)
        self.assertEqual(result["data"]["masters"][0]["name_u"], "Т 2_х обмоточный")
        self.assertEqual(result["data"]["sha256"], hashlib.sha256(contents).hexdigest())
        self.assertEqual(self.docs.calls, [(str(path), 394)])

    def test_invalid_master_is_rejected_without_com(self):
        for name in (
            "../Трансформаторы.vss", "file.vsdm", "C:/Windows/file.vss",
            "Unknown.vss",
        ):
            with self.subTest(name=name):
                result = self.probe(name)
                self.assertIn("unsupported", result["error"])
        self.assertEqual(self.docs.calls, [])

    def test_old_insecure_open_flag_is_rejected_without_com(self):
        result = self.probe("Трансформаторы.vss", flags=18)
        self.assertIn("unsupported", result["error"])
        self.assertEqual(self.docs.calls, [])

    def test_com_open_failure_is_returned_as_diagnostic_not_success(self):
        self.docs.raise_error = True
        (self.originals / "Трансформаторы.vss").write_bytes(b"fixture")
        with patch.object(extension, "Path", lambda name: self.originals):
            result = self.probe("Трансформаторы.vss", flags=394)
        self.assertFalse(result["data"]["opened"])
        self.assertEqual(result["data"]["exception_type"], "RuntimeError")
        self.assertIn("COM read-only", result["data"]["exception_message"])

    def test_readonly_tool_registered_without_generic_mutation_journal(self):
        from app.tools.visio import VISIO_READ_ONLY_TOOLS
        self.assertIn("probe_original_vtd_stencil", VISIO_READ_ONLY_TOOLS)


if __name__ == "__main__":
    unittest.main()
