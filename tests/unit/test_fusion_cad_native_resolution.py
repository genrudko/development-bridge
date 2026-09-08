from __future__ import annotations

import json

import pytest

from app.fusion_cad.scripts import FusionCadScriptBundle


class _Collection:
    def __init__(self, items):
        self._items = list(items)

    @property
    def count(self):
        return len(self._items)

    def item(self, index):
        return self._items[index]


class _Entity:
    def __init__(self, object_type: str):
        self.objectType = object_type


class _Design:
    def __init__(self, result=None, *, raises: Exception | None = None, has_resolver: bool = True):
        self._result = result
        self._raises = raises
        if not has_resolver:
            self.findEntityByToken = None

    def findEntityByToken(self, token):
        if self._raises is not None:
            raise self._raises
        return self._result


def _scope():
    script = FusionCadScriptBundle().build("inspect", {"operation": "test_op"})
    scope: dict = {}
    exec(compile(script, "<native-resolution>", "exec"), scope)  # noqa: S102
    return scope


def _resolve(scope, design, *, token="SECRET_NATIVE_TOKEN", kind="body"):
    return scope["resolve_exact_native_entity"](
        design,
        {"ref": "ent_body_1", "native_token": token, "kind": kind},
        expected_kinds=(kind,),
    )


def test_shared_native_resolver_returns_exact_single_entity():
    scope = _scope()
    body = _Entity("adsk::fusion::BRepBody")
    assert _resolve(scope, _Design(body)) is body
    assert _resolve(scope, _Design(_Collection([body]))) is body


@pytest.mark.parametrize(
    ("design", "expected_code"),
    [
        (_Design(None), "REF_STALE"),
        (_Design(_Collection([])), "REF_STALE"),
        (_Design(_Collection([_Entity("adsk::fusion::BRepBody"), _Entity("adsk::fusion::BRepBody")])), "REF_SPLIT"),
        (_Design(has_resolver=False), "REF_STALE"),
    ],
)
def test_shared_native_resolver_fails_closed_without_one_exact_entity(design, expected_code):
    scope = _scope()
    with pytest.raises(scope["FusionScriptError"]) as exc:
        _resolve(scope, design)
    assert exc.value.code == expected_code
    rendered = json.dumps({"message": str(exc.value), "details": exc.value.details})
    assert "SECRET_NATIVE_TOKEN" not in rendered


def test_shared_native_resolver_rejects_wrong_entity_kind_without_token_leak():
    scope = _scope()
    face = _Entity("adsk::fusion::BRepFace")
    with pytest.raises(scope["FusionScriptError"]) as exc:
        _resolve(scope, _Design(face), kind="body")
    assert exc.value.code == "REF_STALE"
    rendered = json.dumps({"message": str(exc.value), "details": exc.value.details})
    assert "SECRET_NATIVE_TOKEN" not in rendered


def test_shared_native_resolver_sanitizes_native_lookup_exception():
    scope = _scope()
    with pytest.raises(scope["FusionScriptError"]) as exc:
        _resolve(scope, _Design(raises=RuntimeError("driver exploded SECRET_NATIVE_TOKEN")))
    assert exc.value.code == "REF_STALE"
    rendered = json.dumps({"message": str(exc.value), "details": exc.value.details})
    assert "SECRET_NATIVE_TOKEN" not in rendered
    assert "driver exploded" not in rendered


@pytest.mark.parametrize(
    "object_type",
    [
        "adsk::fusion::SketchLine",
        "adsk::fusion::SketchArc",
        "adsk::fusion::SketchCircle",
        "adsk::fusion::SketchEllipse",
        "adsk::fusion::SketchEllipticalArc",
        "adsk::fusion::SketchConicCurve",
        "adsk::fusion::SketchFittedSpline",
        "adsk::fusion::SketchControlPointSpline",
    ],
)
def test_shared_native_resolver_accepts_concrete_sketch_curve_types(object_type):
    scope = _scope()
    curve = _Entity(object_type)
    assert _resolve(scope, _Design(curve), kind="sketch_curve") is curve


def test_shared_native_resolver_sanitizes_collection_count_exception():
    scope = _scope()

    class BrokenCount:
        @property
        def count(self):
            raise RuntimeError("count exploded SECRET_NATIVE_TOKEN")

    with pytest.raises(scope["FusionScriptError"]) as exc:
        _resolve(scope, _Design(BrokenCount()))
    assert exc.value.code == "REF_STALE"
    rendered = json.dumps({"message": str(exc.value), "details": exc.value.details})
    assert "SECRET_NATIVE_TOKEN" not in rendered
    assert "count exploded" not in rendered


def test_shared_native_resolver_sanitizes_collection_item_exception():
    scope = _scope()

    class BrokenItem:
        count = 1

        def item(self, index):
            raise RuntimeError("item exploded SECRET_NATIVE_TOKEN")

    with pytest.raises(scope["FusionScriptError"]) as exc:
        _resolve(scope, _Design(BrokenItem()))
    assert exc.value.code == "REF_STALE"
    rendered = json.dumps({"message": str(exc.value), "details": exc.value.details})
    assert "SECRET_NATIVE_TOKEN" not in rendered
    assert "item exploded" not in rendered


def test_shared_native_resolver_sanitizes_object_type_exception():
    scope = _scope()

    class BrokenKind:
        @property
        def objectType(self):
            raise RuntimeError("kind exploded SECRET_NATIVE_TOKEN")

    with pytest.raises(scope["FusionScriptError"]) as exc:
        _resolve(scope, _Design(BrokenKind()))
    assert exc.value.code == "REF_STALE"
    rendered = json.dumps({"message": str(exc.value), "details": exc.value.details})
    assert "SECRET_NATIVE_TOKEN" not in rendered
    assert "kind exploded" not in rendered


def test_shared_native_resolver_sanitizes_resolver_getter_exception():
    scope = _scope()

    class BrokenDesign:
        @property
        def findEntityByToken(self):
            raise RuntimeError("resolver getter exploded SECRET_NATIVE_TOKEN")

    with pytest.raises(scope["FusionScriptError"]) as exc:
        _resolve(scope, BrokenDesign())
    assert exc.value.code == "REF_STALE"
    rendered = json.dumps({"message": str(exc.value), "details": exc.value.details})
    assert "SECRET_NATIVE_TOKEN" not in rendered
    assert "resolver getter exploded" not in rendered
