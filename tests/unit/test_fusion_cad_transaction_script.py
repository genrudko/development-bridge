from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace

import pytest

from app.fusion_cad.scripts import FusionCadScriptBundle


def _run(payload, runtime):
    script = FusionCadScriptBundle.build("transaction", payload)
    scope = {"__name__": "__main__", **runtime}
    exec(compile(script, "<task13-transaction>", "exec"), scope)  # noqa: S102
    return scope["_output"]


class _Event:
    def __init__(self):
        self.handlers = []

    def add(self, handler):
        self.handlers.append(handler)

    def fire(self, args):
        for handler in tuple(self.handlers):
            handler.notify(args)


def _production_command_runtime(monkeypatch, *, preview):
    import hashlib
    import json

    events = []
    pending_events = []
    lifecycle = {"in_command_created": False}

    class Collection:
        def __init__(self, items=None):
            self._items = list(items or [])

        @property
        def count(self):
            return len(self._items)

        def item(self, index):
            return self._items[index]

    class Attributes(Collection):
        def add(self, group, name, value):
            attr = SimpleNamespace(groupName=group, name=name, value=value)
            self._items.append(attr)
            return attr

        def itemByName(self, group, name):
            for attr in self._items:
                if attr.groupName == group and attr.name == name:
                    return attr
            return None

    class Point:
        def __init__(self, x=0.0, y=0.0, z=0.0):
            self.x = float(x)
            self.y = float(y)
            self.z = float(z)

    class BoundingBox:
        def __init__(self):
            self.minPoint = Point(0, 0, 0)
            self.maxPoint = Point(1, 1, 0)

    class SketchTexts:
        def createInput(self, text, height, position):
            events.append(("createInput", text, height, position.x, position.y, position.z))
            return SimpleNamespace(formattedText=text)

        def add(self, _input):
            events.append("text.add")
            return SimpleNamespace(entityToken="native::text::secret", attributes=Attributes())

    class Sketch:
        def __init__(self, index):
            self.name = f"BridgeText{index}"
            self.entityToken = f"sketch_token_{index}"
            self.isVisible = True
            self.isLightBulbOn = True
            self.profiles = Collection([])
            self.sketchCurves = Collection([])
            self.sketchPoints = Collection([])
            self.geometricConstraints = Collection([])
            self.sketchDimensions = Collection([])
            self.boundingBox = BoundingBox()
            self.attributes = Attributes()
            self.sketchTexts = SketchTexts()

    class TimelineItem:
        def __init__(self, index):
            self.index = index
            self.entityToken = f"timeline_token_{index}"
            self.name = f"BridgeText{index}"
            self.isSuppressed = False
            self.isValid = True
            self.isRolledBack = False
            self.healthStatus = "ok"
            self.attributes = Attributes()
            self.entity = SimpleNamespace(entityToken=f"feature_token_{index}", attributes=Attributes())

    class Sketches(Collection):
        def add(self, plane):
            assert plane == "world-xy"
            index = len(self._items) + 1
            sketch = Sketch(index)
            self._items.append(sketch)
            design.timeline._items.append(TimelineItem(index))
            doc.isModified = True
            events.append("sketch.add")
            return sketch

    root = SimpleNamespace(
        name="Root", id="comp_root", entityToken="comp_root",
        bRepBodies=Collection([]), sketches=None, allOccurrences=Collection([]),
        attributes=Attributes(), xYConstructionPlane="world-xy",
    )
    design = SimpleNamespace(
        rootComponent=root, allComponents=Collection([root]),
        timeline=Collection([]), allParameters=Collection([]),
    )
    root.sketches = Sketches([])

    class Products:
        def itemByClass(self, name):
            return design if "Design" in name else None

    doc = SimpleNamespace(
        dataId="doc_1", name="TestDoc", isModified=False, savedVersion=1,
        attributes=Attributes(), products=Products(),
    )

    class Event:
        def __init__(self):
            self.handlers = []
        def add(self, handler):
            self.handlers.append(handler)
        def fire(self, args):
            for handler in tuple(self.handlers):
                handler.notify(args)

    class Command:
        def __init__(self):
            self.isAutoExecute = True
            self.execute = Event()
            self.destroy = Event()
        def doExecute(self, terminate):
            if lifecycle["in_command_created"]:
                events.append("reentrant_doExecute")
                raise RuntimeError("doExecute called reentrantly from commandCreated")
            events.append(("doExecute", terminate, self.isAutoExecute))
            before_sketches = list(root.sketches._items)
            before_timeline = list(design.timeline._items)
            before_modified = doc.isModified
            args = SimpleNamespace(executeFailed=False)
            self.execute.fire(args)
            events.append(("executeFailed", args.executeFailed))
            if terminate:
                pending_events.append(lambda: self.destroy.fire(SimpleNamespace()))
            if args.executeFailed:
                # Real Fusion finalizes executeFailed rollback on the next main-loop
                # turn after Command.destroy, not synchronously inside doExecute.
                def apply_failed_rollback():
                    root.sketches._items[:] = before_sketches
                    design.timeline._items[:] = before_timeline
                    doc.isModified = before_modified
                    events.append("executeFailed.rollback.applied")
                pending_events.append(apply_failed_rollback)
            return True

    class Definition:
        def __init__(self):
            self.commandCreated = Event()
        def execute(self):
            command = Command()
            def dispatch_created():
                lifecycle["in_command_created"] = True
                try:
                    self.commandCreated.fire(SimpleNamespace(command=command))
                finally:
                    lifecycle["in_command_created"] = False
                events.append("commandCreated.returned")
            pending_events.append(dispatch_created)
            events.append("definition.execute.returned")
            return True
        def deleteMe(self):
            events.append("definition.delete")
            return True

    class Definitions:
        def addButtonDefinition(self, command_id, name, description):
            events.append(("definition.add", command_id, name, description))
            return Definition()

    app = SimpleNamespace(
        userInterface=SimpleNamespace(commandDefinitions=Definitions()),
        activeProduct=design, activeDocument=doc,
    )
    adsk = ModuleType("adsk")
    core = ModuleType("adsk.core")
    fusion = ModuleType("adsk.fusion")
    core.Application = SimpleNamespace(get=lambda: app)
    core.Point3D = SimpleNamespace(create=lambda x, y, z: Point(x, y, z))
    core.CommandCreatedEventHandler = object
    core.CommandEventHandler = object
    fusion.Design = SimpleNamespace(cast=lambda product: product)
    def do_events():
        if pending_events:
            pending_events.pop(0)()

    adsk.doEvents = do_events
    adsk.core = core
    adsk.fusion = fusion
    monkeypatch.setitem(sys.modules, "adsk", adsk)
    monkeypatch.setitem(sys.modules, "adsk.core", core)
    monkeypatch.setitem(sys.modules, "adsk.fusion", fusion)

    canonical = {
        "document": {"document_ref": "doc_1", "name": "TestDoc", "is_modified": False, "saved_version": 1},
        "timeline": [], "components": [{"name": "Root", "id": "comp_root"}],
        "occurrences": [], "bodies": [], "sketches": [], "sketch_texts": [], "parameters": [], "attributes": [],
    }
    baseline_fp = hashlib.sha256(json.dumps(canonical, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    provenance = {
        "creator_tool": "bridge.fusion-cad-agent",
        "creator_operation": "fusion_style:text_create",
        "operation_id": "op_123456789abc",
        "transaction_id": "tx_spike",
        "logical_object_ref": "text_123456789abcdef0",
        "created_revision": "rev_2",
        "tags": [],
    }
    payload = {
        "operation": "preview" if preview else "commit",
        "transaction_id": "tx_spike", "document_ref": "doc_1",
        "expected_fingerprint": baseline_fp,
        "plan": [{
            "action_type": "text_create", "text": "ПЫТОК", "height_mm": 4.0,
            "position": {"x": 10.0, "y": 20.0, "z": 0.0, "frame": {"space": "world"}},
            "metadata_writes": [{"name": "provenance", "value": json.dumps(provenance, ensure_ascii=False, separators=(",", ":"))}],
            "provenance": provenance,
        }],
        "baseline_snapshot": {"structural_hash": baseline_fp, "counts": {"sketches": 0}, "refs": []},
        "_transaction_runtime": "command_definition",
    }
    return payload, {}, {"doc": doc, "design": design, "root": root}, events


def _ptransaction_runtime(monkeypatch, *, preview):
    """Internal opt-in PTransaction fake runtime.

    Simulates dterracino/f360mcp donor semantics for Application.executeTextCommand:
      PTransaction.Start "<fixed-safe-name>" opens a transaction,
      PTransaction.Abort restores the pre-start model state and fingerprint,
      PTransaction.Commit keeps the mutated state. No CommandDefinition surface.
    """
    import hashlib
    import json

    events = []
    state = {
        "in_transaction": False,
        "fp": None,
        "baseline_fp": None,
        "fp_at_start": None,
        "start": None,
        "sketches": [],
        "timeline": [],
        "doc_is_modified": False,
        "provenance": None,
        "text_add_count": 0,
        "fail_on_text_add": False,
        "fail_on_start": False,
        "fail_on_abort": False,
        "fail_on_commit": False,
        "start_result": "1",
        "abort_result": "1",
        "commit_result": "1",
    }

    class Collection:
        def __init__(self, items=None):
            self._items = items if items is not None else []

        @property
        def count(self):
            return len(self._items)

        def item(self, index):
            return self._items[index]

    class Attributes(Collection):
        def add(self, group, name, value):
            attr = SimpleNamespace(groupName=group, name=name, value=value)
            self._items.append(attr)
            if name == "provenance":
                state["provenance"] = value
            return attr

        def itemByName(self, group, name):
            for attr in self._items:
                if attr.groupName == group and attr.name == name:
                    return attr
            return None

    class Point:
        def __init__(self, x=0.0, y=0.0, z=0.0):
            self.x = float(x)
            self.y = float(y)
            self.z = float(z)

    class SketchTexts:
        def createInput(self, text, height, position):
            events.append(("createInput", text, height, position.x, position.y, position.z))
            return SimpleNamespace(formattedText=text)

        def add(self, _input):
            state["text_add_count"] += 1
            events.append("text.add")
            if state["fail_on_text_add"]:
                raise RuntimeError("boom during ptransaction text add")
            return SimpleNamespace(
                entityToken=f"native::ptx::secret_{state['text_add_count']}",
                attributes=Attributes(),
            )

    class Sketch:
        def __init__(self, index):
            self.name = f"BridgeText{index}"
            self.entityToken = f"sketch_token_{index}"
            self.sketchTexts = SketchTexts()

    class Sketches(Collection):
        def add(self, plane):
            assert plane == "world-xy"
            events.append("sketch.add")
            index = len(state["sketches"]) + 1
            sketch = Sketch(index)
            state["sketches"].append(sketch)
            state["timeline"].append(
                SimpleNamespace(index=index, entityToken=f"timeline_token_{index}", name=sketch.name)
            )
            state["doc_is_modified"] = True
            state["fp"] = f"fp_mutated_{index}"
            return sketch

    class Timeline(Collection):
        def __init__(self):
            super().__init__(state["timeline"])

    root = SimpleNamespace(
        name="Root", id="comp_root", entityToken="comp_root",
        xYConstructionPlane="world-xy", sketches=None, bRepBodies=Collection([]),
    )
    design = SimpleNamespace(rootComponent=root, timeline=Timeline(), allComponents=Collection([root]))
    root.sketches = Sketches(state["sketches"])

    class Products:
        def itemByClass(self, name):
            return design if "Design" in name else None

    class Doc:
        dataId = "doc_1"
        name = "TestDoc"
        savedVersion = 1

        @property
        def isModified(self):
            return state["doc_is_modified"]

        @isModified.setter
        def isModified(self, value):
            state["doc_is_modified"] = bool(value)

    doc = Doc()
    doc.attributes = Attributes()
    doc.products = Products()

    canonical = {
        "document": {"document_ref": "doc_1", "name": "TestDoc", "is_modified": False, "saved_version": 1},
        "timeline": [], "components": [{"name": "Root", "id": "comp_root"}],
        "occurrences": [], "bodies": [], "sketches": [], "parameters": [], "attributes": [],
    }
    baseline_fp = hashlib.sha256(json.dumps(canonical, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    state["fp"] = baseline_fp
    state["baseline_fp"] = baseline_fp

    def state_canonical():
        return {
            "document": {
                "document_ref": "doc_1",
                "name": "TestDoc",
                "is_modified": state["doc_is_modified"],
                "saved_version": 1,
            },
            "timeline": [
                {"index": item.index, "id": item.entityToken, "name": item.name}
                for item in state["timeline"]
            ],
            "components": [{"name": "Root", "id": "comp_root"}],
            "occurrences": [],
            "bodies": [],
            "sketches": [{"name": s.name, "id": s.entityToken} for s in state["sketches"]],
            "sketch_texts": [],
            "parameters": [],
            "attributes": [],
        }

    def fingerprint(_payload):
        return state["fp"], state_canonical(), "doc_1"

    class FakeApp:
        activeProduct = design
        activeDocument = doc
        userInterface = None

        def executeTextCommand(self, command):
            events.append(("executeTextCommand", command))
            if command.startswith("PTransaction.Start"):
                if state["fail_on_start"]:
                    raise RuntimeError("boom during ptransaction start")
                if state["start_result"] == "1":
                    assert state["in_transaction"] is False, f"nested PTransaction.Start ({command})"
                    state["in_transaction"] = True
                    state["fp_at_start"] = state["fp"]
                    state["start"] = {
                        "sketches": list(state["sketches"]),
                        "timeline": list(state["timeline"]),
                        "doc_is_modified": state["doc_is_modified"],
                        "provenance": state["provenance"],
                    }
                return state["start_result"]
            elif command == "PTransaction.Abort":
                if state["fail_on_abort"]:
                    raise RuntimeError("boom during ptransaction abort")
                if state["abort_result"] == "1":
                    assert state["in_transaction"] is True, "PTransaction.Abort without an active transaction"
                    state["in_transaction"] = False
                    start = state["start"]
                    if start is not None:
                        state["sketches"][:] = start["sketches"]
                        state["timeline"][:] = start["timeline"]
                        state["doc_is_modified"] = start["doc_is_modified"]
                        state["provenance"] = start["provenance"]
                    state["fp"] = state["fp_at_start"]
                return state["abort_result"]
            elif command == "PTransaction.Commit":
                assert state["in_transaction"] is True, "PTransaction.Commit without an active transaction"
                if state["fail_on_commit"]:
                    raise RuntimeError("boom during ptransaction commit")
                if state["commit_result"] == "1":
                    state["in_transaction"] = False
                    state["start"] = None
                return state["commit_result"]
            else:
                raise AssertionError(f"Unexpected text command {command!r}")

    app = FakeApp()

    adsk = ModuleType("adsk")
    core = ModuleType("adsk.core")
    fusion = ModuleType("adsk.fusion")
    core.Application = SimpleNamespace(get=lambda: app)
    core.Point3D = SimpleNamespace(create=lambda x, y, z: Point(x, y, z))
    fusion.Design = SimpleNamespace(cast=lambda product: product)
    adsk.core = core
    adsk.fusion = fusion
    monkeypatch.setitem(sys.modules, "adsk", adsk)
    monkeypatch.setitem(sys.modules, "adsk.core", core)
    monkeypatch.setitem(sys.modules, "adsk.fusion", fusion)

    provenance = {
        "creator_tool": "bridge.fusion-cad-agent",
        "creator_operation": "fusion_style:text_create",
        "operation_id": "op_123456789abc",
        "transaction_id": "tx_spike",
        "logical_object_ref": "text_123456789abcdef0",
        "created_revision": "rev_2",
        "tags": [],
    }
    payload = {
        "operation": "preview" if preview else "commit",
        "transaction_id": "tx_spike", "document_ref": "doc_1",
        "expected_fingerprint": baseline_fp,
        "plan": [{
            "action_type": "text_create", "text": "ПЫТОК", "height_mm": 4.0,
            "position": {"x": 10.0, "y": 20.0, "z": 0.0, "frame": {"space": "world"}},
            "metadata_writes": [{"name": "provenance", "value": json.dumps(provenance, ensure_ascii=False, separators=(",", ":"))}],
            "provenance": provenance,
        }],
        "baseline_snapshot": {"structural_hash": baseline_fp, "counts": {"sketches": 0}, "refs": []},
        "_transaction_runtime": "ptransaction",
    }
    state["doc"] = doc
    state["design"] = design
    state["root"] = root
    return payload, {"_transaction_fingerprint_primitive": fingerprint}, state, events


def test_production_preview_uses_command_execute_failed_without_transaction_hooks(monkeypatch):
    payload, runtime, state, events = _production_command_runtime(monkeypatch, preview=True)
    result = _run(payload, runtime)

    assert result["status"] == "succeeded"
    assert result["data"]["preview"] is True
    assert result["data"]["preview_refs_durable"] is False
    assert state["root"].sketches.count == 0
    assert state["design"].timeline.count == 0
    assert state["doc"].isModified is False
    assert ("doExecute", True, False) in events
    assert "reentrant_doExecute" not in events
    assert events.index("commandCreated.returned") < events.index(("doExecute", True, False))
    assert ("executeFailed", True) in events
    assert "executeFailed.rollback.applied" in events
    assert events.index("executeFailed.rollback.applied") < events.index("definition.delete")
    assert ("createInput", "ПЫТОК", 0.4, 1.0, 2.0, 0.0) in events


def test_production_commit_persists_and_reads_provenance_and_returns_internal_hint(monkeypatch):
    payload, runtime, state, events = _production_command_runtime(monkeypatch, preview=False)
    result = _run(payload, runtime)

    assert result["status"] == "succeeded"
    assert result["data"]["persisted_provenance"] == payload["plan"][0]["provenance"]
    assert result["data"]["internal_ref_hints"] == [
        {"kind": "sketch_text", "native_token": "native::text::secret"}
    ]
    assert result["changed_refs"] == []
    assert state["doc"].isModified is True
    assert state["root"].sketches.count == 1
    assert state["design"].timeline.count == 1
    assert "reentrant_doExecute" not in events
    assert events.index("commandCreated.returned") < events.index(("doExecute", True, False))
    assert ("executeFailed", False) in events


def test_preview_applies_snapshot_validates_then_aborts_without_durable_evidence():
    events = []
    state = {"fingerprint": "fp_base", "refs": ["ent_body_existing"], "metadata": []}
    before = {
        "structural_hash": "h_base",
        "counts": {"bodies": 1, "sketches": 0},
        "refs": ["ent_body_existing"],
    }

    def fingerprint(_payload):
        return state["fingerprint"], {}, "doc_1"

    def begin(_payload):
        events.append("begin")

    def apply(plan):
        events.append(("apply", plan))
        state.update(
            fingerprint="fp_preview",
            refs=["ent_body_existing", "ent_sketch_preview"],
            metadata=["provenance"],
        )
        return {
            "refs": ["ent_sketch_preview"],
            "provenance": {"transaction_id": "tx_spike"},
        }

    def snapshot(_payload):
        events.append("snapshot")
        return {
            "structural_hash": "h_preview",
            "counts": {"bodies": 1, "sketches": 1},
            "refs": list(state["refs"]),
        }

    def validate(_payload):
        events.append("validate")
        return {"status": "passed", "errors": []}

    def abort(_payload):
        events.append("abort")
        state.update(fingerprint="fp_base", refs=["ent_body_existing"], metadata=[])

    plan = [
        {
            "action_type": "text_create",
            "text": "ПЫТОК",
            "provenance": {"transaction_id": "tx_spike"},
        }
    ]
    result = _run(
        {
            "operation": "preview",
            "transaction_id": "tx_spike",
            "document_ref": "doc_1",
            "expected_fingerprint": "fp_base",
            "plan": plan,
            "baseline_snapshot": before,
        },
        {
            "_transaction_fingerprint_primitive": fingerprint,
            "_transaction_begin_primitive": begin,
            "_transaction_apply_plan_primitive": apply,
            "_transaction_snapshot_primitive": snapshot,
            "_transaction_validate_primitive": validate,
            "_transaction_abort_primitive": abort,
        },
    )
    assert events == ["begin", ("apply", plan), "snapshot", "validate", "abort"]
    assert state == {
        "fingerprint": "fp_base",
        "refs": ["ent_body_existing"],
        "metadata": [],
    }
    assert result["data"]["preview_refs"] == ["ent_sketch_preview"]
    assert result["data"]["preview_refs_durable"] is False
    assert result["diff"]["refs"]["added"] == ["ent_sketch_preview"]


def test_commit_rechecks_then_replays_exact_plan_once_with_no_metadata_followup():
    events = []
    state = {"fingerprint": "fp_base"}
    plan = [
        {
            "action_type": "text_create",
            "text": "ПЫТОК",
            "metadata_writes": [{"name": "provenance"}],
        }
    ]

    def fingerprint(_payload):
        events.append("fingerprint")
        return state["fingerprint"], {}, "doc_1"

    def begin(_payload):
        events.append("begin")

    def apply(received):
        events.append(("apply", received))
        state["fingerprint"] = "fp_committed"
        return {
            "refs": ["ent_text_committed"],
            "provenance": {"transaction_id": "tx_spike"},
            "same_operation_provenance": True,
        }

    def finish(_payload):
        events.append("commit")

    result = _run(
        {
            "operation": "commit",
            "transaction_id": "tx_spike",
            "document_ref": "doc_1",
            "expected_fingerprint": "fp_base",
            "plan": plan,
        },
        {
            "_transaction_fingerprint_primitive": fingerprint,
            "_transaction_begin_primitive": begin,
            "_transaction_apply_plan_primitive": apply,
            "_transaction_snapshot_primitive": lambda payload: {"structural_hash": "fp_committed", "counts": {}, "refs": ["ent_text_committed"]},
            "_transaction_commit_primitive": finish,
        },
    )
    assert events == ["fingerprint", "begin", ("apply", plan), "commit", "fingerprint"]
    assert result["data"]["replayed_plan"] == plan
    assert result["data"]["same_command_provenance"] is True


def test_preview_rejects_nondefault_text_option_before_apply(monkeypatch):
    payload, runtime, state, events = _ptransaction_runtime(monkeypatch, preview=True)
    payload["plan"][0]["font"] = "Comic Sans MS"
    result = _run(payload, runtime)

    assert result["status"] == "failed"
    assert result["error"]["code"] == "CAPABILITY_UNAVAILABLE"
    assert result["error"]["details"]["applied"] is False
    assert events == []
    assert state["text_add_count"] == 0


def test_ptransaction_post_commit_fingerprint_exception_is_uncertain(monkeypatch):
    payload, runtime, state, events = _ptransaction_runtime(monkeypatch, preview=False)
    original_fingerprint = runtime["_transaction_fingerprint_primitive"]
    calls = {"count": 0}

    def fingerprint(payload):
        calls["count"] += 1
        if calls["count"] == 3:
            raise RuntimeError("post-commit fingerprint unavailable")
        return original_fingerprint(payload)

    runtime["_transaction_fingerprint_primitive"] = fingerprint
    result = _run(payload, runtime)

    assert state["text_add_count"] == 1
    commands = [e[1] for e in events if isinstance(e, tuple) and e[0] == "executeTextCommand"]
    assert commands == ['PTransaction.Start "bridge_cad_transaction"', "PTransaction.Commit"]
    assert result["status"] == "failed"
    assert result["error"]["code"] == "OPERATION_UNCERTAIN"


def test_primitive_commit_post_commit_unchanged_fingerprint_is_uncertain():
    events = []
    plan = [{"action_type": "text_create"}]

    def fingerprint(_payload):
        events.append("fingerprint")
        return "fp_base", {}, "doc_1"

    def apply(received):
        events.append(("apply", received))
        return {
            "refs": [],
            "provenance": {"transaction_id": "tx_spike"},
            "same_operation_provenance": True,
        }

    result = _run(
        {
            "operation": "commit",
            "transaction_id": "tx_spike",
            "document_ref": "doc_1",
            "expected_fingerprint": "fp_base",
            "plan": plan,
        },
        {
            "_transaction_fingerprint_primitive": fingerprint,
            "_transaction_begin_primitive": lambda payload: events.append("begin"),
            "_transaction_apply_plan_primitive": apply,
            "_transaction_snapshot_primitive": lambda payload: {"structural_hash": "fp_base", "counts": {}, "refs": []},
            "_transaction_commit_primitive": lambda payload: events.append("commit"),
        },
    )

    assert events == ["fingerprint", "begin", ("apply", plan), "commit", "fingerprint"]
    assert result["status"] == "failed"
    assert result["error"]["code"] == "OPERATION_UNCERTAIN"


def test_commit_rejects_nonopaque_generated_refs():
    state = {"fingerprint": "fp_base"}

    def fingerprint(_payload):
        return state["fingerprint"], {}, "doc_1"

    def apply(_plan):
        state["fingerprint"] = "fp_committed"
        return {
            "refs": ["native-token-secret"],
            "provenance": {"transaction_id": "tx_spike"},
            "same_operation_provenance": True,
        }

    result = _run(
        {
            "operation": "commit",
            "transaction_id": "tx_spike",
            "document_ref": "doc_1",
            "expected_fingerprint": "fp_base",
            "plan": [{"action_type": "text_create"}],
        },
        {
            "_transaction_fingerprint_primitive": fingerprint,
            "_transaction_begin_primitive": lambda payload: None,
            "_transaction_apply_plan_primitive": apply,
            "_transaction_commit_primitive": lambda payload: None,
        },
    )
    assert result["status"] == "failed"
    assert result["error"]["code"] == "FUSION_API_ERROR"
    assert "native-token-secret" not in str(result)


def test_ptransaction_preview_orders_start_mutation_abort_and_restores_baseline(monkeypatch):
    payload, runtime, state, events = _ptransaction_runtime(monkeypatch, preview=True)
    result = _run(payload, runtime)

    assert result["status"] == "succeeded"
    text_commands = [
        entry[1]
        for entry in events
        if isinstance(entry, tuple) and entry[0] == "executeTextCommand"
    ]
    assert text_commands == [
        'PTransaction.Start "bridge_cad_transaction"',
        "PTransaction.Abort",
    ]
    assert events.index(("executeTextCommand", 'PTransaction.Start "bridge_cad_transaction"')) < events.index("sketch.add")
    assert events.index("sketch.add") < events.index("text.add")
    assert events.index("text.add") < events.index(("executeTextCommand", "PTransaction.Abort"))
    assert "definition.add" not in events
    assert "doExecute" not in events
    assert "commandCreated.returned" not in events

    assert result["data"]["preview"] is True
    assert result["data"]["preview_refs_durable"] is False
    assert result["data"]["preview_refs"] == []
    assert result["data"]["provenance_durable"] is False
    assert result["data"]["preview_snapshot"]["counts"]["sketches"] == 1
    assert state["fp"] == payload["expected_fingerprint"]
    assert state["sketches"] == []
    assert state["timeline"] == []
    assert state["doc_is_modified"] is False
    assert state["in_transaction"] is False
    assert state["provenance"] is None
    assert result["data"]["provenance"] == payload["plan"][0]["provenance"]


def test_ptransaction_preview_collects_mutated_validation_before_abort(monkeypatch):
    payload, runtime, state, events = _ptransaction_runtime(monkeypatch, preview=True)

    def collect_validation(_payload):
        events.append("validation.collect")
        assert state["in_transaction"] is True
        assert len(state["sketches"]) == 1
        return {
            "document_ref": "doc_1", "features": [],
            "sketches": [{"kind": "sketch", "valid": False, "health": "error"}],
            "references": [{"kind": "sketch", "state": "broken"}],
            "bodies": [], "text_outputs": [],
            "timeline": {"available": True, "rolled_back": False}, "limitations": [],
        }

    runtime["_transaction_validation_evidence_primitive"] = collect_validation
    result = _run(payload, runtime)

    assert result["status"] == "succeeded"
    assert result["validation"]["sketches"][0]["health"] == "error"
    abort_event = ("executeTextCommand", "PTransaction.Abort")
    assert events.index("text.add") < events.index("validation.collect") < events.index(abort_event)


def test_ptransaction_preview_fails_closed_when_validation_evidence_unavailable(monkeypatch):
    payload, runtime, state, events = _ptransaction_runtime(monkeypatch, preview=True)

    def unavailable(_payload):
        events.append("validation.collect")

    runtime["_transaction_validation_evidence_primitive"] = unavailable
    result = _run(payload, runtime)

    assert result["status"] == "failed"
    assert result["error"]["code"] == "CAPABILITY_UNAVAILABLE"
    commands = [e[1] for e in events if isinstance(e, tuple) and e[0] == "executeTextCommand"]
    assert commands == ['PTransaction.Start "bridge_cad_transaction"', "PTransaction.Abort"]
    assert state["in_transaction"] is False


def test_ptransaction_commit_orders_start_mutation_commit_and_persists_once(monkeypatch):
    import json

    payload, runtime, state, events = _ptransaction_runtime(monkeypatch, preview=False)
    result = _run(payload, runtime)

    assert result["status"] == "succeeded"
    text_commands = [
        entry[1]
        for entry in events
        if isinstance(entry, tuple) and entry[0] == "executeTextCommand"
    ]
    assert text_commands == [
        'PTransaction.Start "bridge_cad_transaction"',
        "PTransaction.Commit",
    ]
    assert "PTransaction.Abort" not in text_commands
    assert events.index(("executeTextCommand", 'PTransaction.Start "bridge_cad_transaction"')) < events.index("sketch.add")
    assert events.index("sketch.add") < events.index("text.add")
    assert events.index("text.add") < events.index(("executeTextCommand", "PTransaction.Commit"))
    assert "definition.add" not in events
    assert "doExecute" not in events
    assert "commandCreated.returned" not in events

    assert result["data"]["applied"] is True
    assert state["in_transaction"] is False
    assert state["text_add_count"] == 1
    assert len(state["sketches"]) == 1
    assert len(state["timeline"]) == 1
    assert state["doc_is_modified"] is True
    assert state["fp"] != payload["expected_fingerprint"]
    assert json.loads(state["provenance"]) == payload["plan"][0]["provenance"]
    assert result["data"]["internal_ref_hints"] == [
        {"kind": "sketch_text", "native_token": "native::ptx::secret_1"}
    ]
    assert result["data"]["same_command_provenance"] is True
    assert result["data"]["same_operation_provenance"] is True
    assert result["data"]["persisted_provenance"] == payload["plan"][0]["provenance"]
    assert result["data"]["refs"] == []
    assert "native::ptx::secret_1" not in json.dumps(result["changed_refs"])


def test_ptransaction_is_default_without_selector_after_live_acceptance(monkeypatch):
    payload, runtime, state, events = _ptransaction_runtime(monkeypatch, preview=False)
    payload.pop("_transaction_runtime", None)
    result = _run(payload, runtime)

    assert result["status"] == "succeeded"
    text_commands = [
        entry[1]
        for entry in events
        if isinstance(entry, tuple) and entry[0] == "executeTextCommand"
    ]
    assert text_commands == [
        'PTransaction.Start "bridge_cad_transaction"',
        "PTransaction.Commit",
    ]
    assert state["in_transaction"] is False
    assert state["text_add_count"] == 1


def test_command_definition_runtime_requires_explicit_internal_selector(monkeypatch):
    payload, runtime, state, events = _production_command_runtime(monkeypatch, preview=False)
    assert payload["_transaction_runtime"] == "command_definition"
    result = _run(payload, runtime)

    assert result["status"] == "succeeded"
    assert ("doExecute", True, False) in events
    assert state["root"].sketches.count == 1


def test_unknown_transaction_runtime_selector_fails_closed(monkeypatch):
    payload, runtime, state, events = _ptransaction_runtime(monkeypatch, preview=False)
    payload["_transaction_runtime"] = "mystery_runtime"
    result = _run(payload, runtime)

    assert result["status"] == "failed"
    assert result["error"]["code"] == "INVALID_ARGUMENT"
    assert state["in_transaction"] is False
    assert state["text_add_count"] == 0
    assert events == []


@pytest.mark.parametrize("operation", ["begin", "stage", "status", "abort", "rollback"])
def test_unknown_transaction_runtime_selector_fails_closed_for_non_native_ops(monkeypatch, operation):
    payload, runtime, state, events = _ptransaction_runtime(monkeypatch, preview=False)
    payload["operation"] = operation
    payload["_transaction_runtime"] = "mystery_runtime"
    result = _run(payload, runtime)

    assert result["status"] == "failed"
    assert result["error"]["code"] == "INVALID_ARGUMENT"
    assert state["in_transaction"] is False
    assert state["text_add_count"] == 0
    assert events == []


@pytest.mark.parametrize("operation", ["preview", "commit"])
def test_unknown_transaction_runtime_selector_fails_closed_before_primitive_routing(monkeypatch, operation):
    payload, runtime, state, events = _ptransaction_runtime(monkeypatch, preview=(operation == "preview"))
    payload["operation"] = operation
    payload["_transaction_runtime"] = "mystery_runtime"
    runtime["_transaction_begin_primitive"] = lambda _payload: None
    result = _run(payload, runtime)

    assert result["status"] == "failed"
    assert result["error"]["code"] == "INVALID_ARGUMENT"
    assert state["in_transaction"] is False
    assert state["text_add_count"] == 0
    assert events == []


def test_ptransaction_exact_plan_validation_runs_before_transaction_start(monkeypatch):
    payload, runtime, state, events = _ptransaction_runtime(monkeypatch, preview=False)
    payload["plan"] = [{
        "action_type": "text_create", "text": "ПЫТОК", "height_mm": 4.0,
        "position": {"x": 1.0, "y": 1.0, "z": 1.0, "frame": {"space": "world"}},
        "metadata_writes": payload["plan"][0]["metadata_writes"],
        "provenance": payload["plan"][0]["provenance"],
    }]
    result = _run(payload, runtime)

    assert result["status"] == "failed"
    assert result["error"]["code"] == "CAPABILITY_UNAVAILABLE"
    assert events == []
    assert state["in_transaction"] is False


def test_ptransaction_exception_between_start_and_terminal_aborts_fail_closed(monkeypatch):
    payload, runtime, state, events = _ptransaction_runtime(monkeypatch, preview=False)
    state["fail_on_text_add"] = True
    result = _run(payload, runtime)

    assert result["status"] == "failed"
    assert result["error"]["code"] == "FUSION_API_ERROR"
    assert "boom during ptransaction text add" in result["error"]["message"]
    text_commands = [
        entry[1]
        for entry in events
        if isinstance(entry, tuple) and entry[0] == "executeTextCommand"
    ]
    assert text_commands == [
        'PTransaction.Start "bridge_cad_transaction"',
        "PTransaction.Abort",
    ]
    assert events.index(("executeTextCommand", "PTransaction.Abort")) > events.index("text.add")
    assert state["in_transaction"] is False


def test_ptransaction_commit_exception_stops_immediately_and_reports_uncertain(monkeypatch):
    payload, runtime, state, events = _ptransaction_runtime(monkeypatch, preview=False)
    state["fail_on_commit"] = True
    result = _run(payload, runtime)

    assert result["status"] == "failed"
    assert result["error"]["code"] == "OPERATION_UNCERTAIN"
    assert "commit outcome is uncertain" in result["error"]["message"]
    text_commands = [
        entry[1]
        for entry in events
        if isinstance(entry, tuple) and entry[0] == "executeTextCommand"
    ]
    assert text_commands == [
        'PTransaction.Start "bridge_cad_transaction"',
        "PTransaction.Commit",
    ]
    assert state["in_transaction"] is True


def test_ptransaction_rendered_script_compiles_for_all_seven_operations():
    from app.fusion_cad.scripts import FusionCadScriptBundle

    bundle = FusionCadScriptBundle()
    for op in ("begin", "stage", "preview", "commit", "abort", "rollback", "status"):
        payload = {
            "operation": op,
            "transaction_id": "tx_spike",
            "document_ref": "doc_1",
            "expected_fingerprint": "fp",
            "plan": [{"action_type": "text_create"}],
            "_transaction_runtime": "ptransaction",
        }
        script = bundle.build("transaction", payload)
        compiled = compile(script, f"<tx-{op}>", "exec")
        assert compiled is not None
        assert "_transaction_runtime" in script


def test_ptransaction_failed_start_never_mutates(monkeypatch):
    payload, runtime, state, events = _ptransaction_runtime(monkeypatch, preview=False)
    state["start_result"] = "0"
    result = _run(payload, runtime)

    assert result["status"] == "failed"
    assert result["error"]["code"] == "CAPABILITY_UNAVAILABLE"
    assert state["text_add_count"] == 0
    assert state["sketches"] == []
    assert state["in_transaction"] is False
    commands = [e[1] for e in events if isinstance(e, tuple) and e[0] == "executeTextCommand"]
    assert commands == ['PTransaction.Start "bridge_cad_transaction"']


def test_ptransaction_start_exception_is_uncertain_and_never_mutates(monkeypatch):
    payload, runtime, state, events = _ptransaction_runtime(monkeypatch, preview=False)
    state["fail_on_start"] = True
    result = _run(payload, runtime)

    assert result["status"] == "failed"
    assert result["error"]["code"] == "OPERATION_UNCERTAIN"
    assert state["text_add_count"] == 0
    commands = [e[1] for e in events if isinstance(e, tuple) and e[0] == "executeTextCommand"]
    assert commands == ['PTransaction.Start "bridge_cad_transaction"']


def test_ptransaction_preview_failed_abort_is_uncertain_without_retry(monkeypatch):
    payload, runtime, state, events = _ptransaction_runtime(monkeypatch, preview=True)
    state["abort_result"] = "0"
    result = _run(payload, runtime)

    assert result["status"] == "failed"
    assert result["error"]["code"] == "OPERATION_UNCERTAIN"
    assert state["text_add_count"] == 1
    commands = [e[1] for e in events if isinstance(e, tuple) and e[0] == "executeTextCommand"]
    assert commands == ['PTransaction.Start "bridge_cad_transaction"', "PTransaction.Abort"]


def test_ptransaction_commit_failed_response_is_uncertain(monkeypatch):
    payload, runtime, state, events = _ptransaction_runtime(monkeypatch, preview=False)
    state["commit_result"] = "0"
    result = _run(payload, runtime)

    assert result["status"] == "failed"
    assert result["error"]["code"] == "OPERATION_UNCERTAIN"
    assert state["text_add_count"] == 1
    commands = [e[1] for e in events if isinstance(e, tuple) and e[0] == "executeTextCommand"]
    assert commands == ['PTransaction.Start "bridge_cad_transaction"', "PTransaction.Commit"]
    assert state["in_transaction"] is True


def test_ptransaction_mutation_error_with_failed_cleanup_abort_is_uncertain(monkeypatch):
    payload, runtime, state, events = _ptransaction_runtime(monkeypatch, preview=False)
    state["fail_on_text_add"] = True
    state["abort_result"] = "0"
    result = _run(payload, runtime)

    assert result["status"] == "failed"
    assert result["error"]["code"] == "OPERATION_UNCERTAIN"
    commands = [e[1] for e in events if isinstance(e, tuple) and e[0] == "executeTextCommand"]
    assert commands == ['PTransaction.Start "bridge_cad_transaction"', "PTransaction.Abort"]
