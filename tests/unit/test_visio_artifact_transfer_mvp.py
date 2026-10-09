"""Native-file Visio transfer MVP: integrity, bounded paths, segmented transport."""
import asyncio
import base64
import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from managed.visio.artifact_receiver import ArtifactReceiver, checked_name, validate_package
from app.tools.visio_artifact_transfer import outbox_file, transfer_artifact


FIXTURE = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "visio_transfer_minimal.vsdx"


class ReceiverTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.receiver = ArtifactReceiver(self.root / "received")
        self.raw = FIXTURE.read_bytes()
        self.sha = hashlib.sha256(self.raw).hexdigest()
        self.tid = "a" * 32

    def feed(self, raw=None, sha=None, name="Контрольная схема.vsdx", final=True,
             offset=0, tid=None):
        raw = self.raw if raw is None else raw
        return self.receiver.receive(
            transfer_id=tid or self.tid, file_name=name, offset=offset,
            content_b64=base64.b64encode(raw).decode("ascii"),
            total_size=len(self.raw), sha256=self.sha if sha is None else sha, final=final,
        )

    def test_valid_unicode_roundtrip_and_immutable(self):
        done = self.feed()
        self.assertTrue(done["complete"])
        status = self.receiver.status(self.tid)
        self.assertEqual(status["sha256"], self.sha)
        self.assertEqual(Path(status["path"]).read_bytes(), self.raw)
        with self.assertRaises(ValueError):
            self.feed()

    def test_fail_closed_on_bad_hash_and_partial(self):
        with self.assertRaises(ValueError):
            self.feed(sha="0"*64)
        self.assertFalse(self.receiver.status(self.tid)["complete"])

    def test_reject_invalid_basename(self):
        for name in ["../e.vsdx", "C:bad.vsdm", "evil.exe", "x\\y.vsdx",
                     ".hidden.vsdx", "bad.vsdx.", "abc.vss"]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                checked_name(name)

    def test_reject_invalid_package_even_valid_digest(self):
        tid = "b"*32
        data = b"%PDF-1.3 test"
        with self.assertRaises(ValueError):
            self.receiver.receive(transfer_id=tid, file_name="fake.vsdx", offset=0,
                                  content_b64=base64.b64encode(data).decode(),
                                  total_size=len(data),
                                  sha256=hashlib.sha256(data).hexdigest(), final=True)

    def test_partial_sequential_and_boundary(self):
        mid = len(self.raw)//2
        self.receiver.receive(transfer_id=self.tid, file_name="part.vsdx",offset=0,
                              content_b64=base64.b64encode(self.raw[:mid]).decode(),
                              total_size=len(self.raw), sha256=self.sha, final=False)
        with self.assertRaises(ValueError):
            self.receiver.receive(transfer_id=self.tid, file_name="part.vsdx",offset=0,
                                  content_b64=base64.b64encode(self.raw[mid:]).decode(),
                                  total_size=len(self.raw), sha256=self.sha, final=True)
        result=self.receiver.receive(transfer_id=self.tid,file_name="part.vsdx",offset=mid,
                                    content_b64=base64.b64encode(self.raw[mid:]).decode(),
                                    total_size=len(self.raw),sha256=self.sha,final=True)
        self.assertTrue(result["complete"])

    def test_modified_file_detected(self):
        self.feed()
        p=Path(self.receiver.status(self.tid)["path"])
        p.write_bytes(self.raw+b"x")
        with self.assertRaises(ValueError):
            self.receiver.status(self.tid)

    def test_server_rejects_symlink_escape(self):
        outbox=self.root/"outbox"
        outbox.mkdir()
        target=self.root/"elsewhere.vsdx"
        target.write_bytes(self.raw)
        (outbox/"safe.vsdx").symlink_to(target)
        with self.assertRaises(ValueError):
            outbox_file(outbox, "safe.vsdx")


class FakeDesktop:
    def __init__(self, directory):
        self.settings=SimpleNamespace(result_artifact_directory=directory/"results")
        self.receiver=ArtifactReceiver(directory/"received")
        self.calls=[]
        self.document_opened=False

    async def call(self,node_id,name,args,journal):
        self.calls.append(name)
        if name=="stage_visio_artifact_chunk":
            value=self.receiver.receive(**args)
        elif name=="visio_artifact_status":
            value=self.receiver.status(args["transfer_id"])
        elif name=="open_received_visio_artifact":
            value=self.receiver.status(args["transfer_id"])
            value={"transfer_id": args["transfer_id"], "sha256": value["sha256"],
                   "mode": "read_only_macro_disabled",
                   "document_name": value["file_name"]}
            self.document_opened=True
        else:
            raise ValueError(name)
        return {"content":[{"type":"text","text":json.dumps(value)}],"isError":False}


class SenderRoundTripTest(unittest.IsolatedAsyncioTestCase):
    async def test_server_to_windows_simulation(self):
        with tempfile.TemporaryDirectory() as directory:
            directory=Path(directory)
            desktop=FakeDesktop(directory)
            outbox=directory/"visio-outbox"
            outbox.mkdir()
            (outbox/"Pilot.vsdx").write_bytes(FIXTURE.read_bytes())
            container=SimpleNamespace(desktop_nodes=desktop)
            result=await transfer_artifact(container,node_id="visio-workstation",
                                           file_name="Pilot.vsdx",open_in_visio=True,
                                           error_reader=lambda response: None)
            self.assertTrue(result["opened"])
            self.assertTrue(desktop.document_opened)
            self.assertEqual(desktop.calls, ["stage_visio_artifact_chunk",
                                             "visio_artifact_status",
                                             "open_received_visio_artifact"])
            self.assertEqual(desktop.receiver.status(result["transfer_id"])["sha256"],
                             result["sha256"])

    async def test_server_checks_returned_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            directory=Path(directory)
            class LyingDesktop(FakeDesktop):
                async def call(self, node_id, name, args, journal):
                    result = await super().call(node_id, name, args, journal)
                    if name == "visio_artifact_status":
                        entry=json.loads(result["content"][0]["text"])
                        entry["sha256"]="0"*64
                        result["content"][0]["text"]=json.dumps(entry)
                    return result
            desktop=LyingDesktop(directory)
            outbox=directory/"visio-outbox"
            outbox.mkdir()
            (outbox/"Pilot.vsdx").write_bytes(FIXTURE.read_bytes())
            with self.assertRaisesRegex(RuntimeError, "receipt mismatch"):
                await transfer_artifact(SimpleNamespace(desktop_nodes=desktop),
                                        node_id="visio-workstation", file_name="Pilot.vsdx",
                                        open_in_visio=True, error_reader=lambda response: None)
            self.assertFalse(desktop.document_opened)

    async def test_multi_chunk_transport(self):
        with tempfile.TemporaryDirectory() as directory:
            directory=Path(directory)
            desktop=FakeDesktop(directory)
            outbox=directory/"visio-outbox"
            outbox.mkdir()
            # Preserve every existing Visio OPC part. Add only ignorable XML
            # whitespace to a known page, then store that part uncompressed;
            # the earlier orphan-media test was rejected by native Visio.
            from zipfile import ZipFile, ZIP_STORED
            from xml.etree import ElementTree as ET
            out=outbox/"Large.vsdx"
            with ZipFile(FIXTURE) as orig, ZipFile(out, "w") as large:
                for info in orig.infolist():
                    raw = orig.read(info.filename)
                    if info.filename == "visio/pages/page1.xml":
                        closing = raw.rfind(b"</")
                        assert closing > 0
                        raw = raw[:closing] + b" "*350000 + raw[closing:]
                        ET.fromstring(raw)
                        large.writestr(info, raw, compress_type=ZIP_STORED)
                    else:
                        large.writestr(info, raw)
            result=await transfer_artifact(SimpleNamespace(desktop_nodes=desktop),
                                           node_id="visio-workstation", file_name="Large.vsdx",
                                           open_in_visio=True, error_reader=lambda response: None)
            self.assertEqual(result["chunks"], 3)
            self.assertEqual(desktop.calls.count("stage_visio_artifact_chunk"),3)
            self.assertTrue(desktop.document_opened)

    async def test_transfer_only(self):
        with tempfile.TemporaryDirectory() as directory:
            directory=Path(directory)
            desktop=FakeDesktop(directory)
            outbox=directory/"visio-outbox"
            outbox.mkdir()
            (outbox/"Pilot.vsdx").write_bytes(FIXTURE.read_bytes())
            result=await transfer_artifact(SimpleNamespace(desktop_nodes=desktop),
                                           node_id="visio-workstation",
                                           file_name="Pilot.vsdx",open_in_visio=False,
                                           error_reader=lambda response: None)
            self.assertFalse(result["opened"])
            self.assertFalse(desktop.document_opened)


if __name__ == "__main__":
    unittest.main()
