import asyncio

import pytest

from app.blender_hub.catalog import (
    DuplicateToolName,
    NamespacedToolCatalog,
    ProviderState,
    ProviderTool,
    is_mutating,
)


async def _return_provider(arguments: dict[str, object]) -> object:
    return arguments


def tool(name: str, metadata: object = None) -> ProviderTool:
    return ProviderTool(name=name, handler=_return_provider, metadata=metadata)


def test_catalog_registers_namespaced_tools_and_rejects_duplicate_atomically():
    catalog = NamespacedToolCatalog()
    catalog.register_provider("dcc-main", "dcc", [tool("scene.get"), tool("object.list")])

    with pytest.raises(DuplicateToolName, match=r"dcc\.scene\.get"):
        catalog.register_provider(
            "dcc-shadow", "dcc", [tool("new.tool"), tool("scene.get")]
        )

    assert [entry.qualified_name for entry in catalog.list_tools()] == [
        "dcc.object.list",
        "dcc.scene.get",
    ]


@pytest.mark.asyncio
async def test_offline_provider_is_isolated_from_catalog_and_healthy_provider():
    catalog = NamespacedToolCatalog()
    catalog.register_provider(
        "dcc-main", "dcc", [tool("scene.get", {"readOnlyHint": True})]
    )
    catalog.register_provider(
        "research-main", "research", [tool("lookup", {"readOnlyHint": True})]
    )
    catalog.set_provider_status("dcc-main", ProviderState.OFFLINE, "connection refused")

    assert await catalog.invoke("research.lookup", {"query": "mesh"}) == {
        "query": "mesh"
    }
    statuses = {status.provider_id: status for status in catalog.provider_statuses()}
    assert statuses["dcc-main"].state is ProviderState.OFFLINE
    assert statuses["dcc-main"].error == "connection refused"
    assert statuses["research-main"].state is ProviderState.ONLINE
    assert {entry.qualified_name for entry in catalog.list_tools()} == {
        "dcc.scene.get",
        "research.lookup",
    }


@pytest.mark.parametrize(
    ("metadata", "expected"),
    [
        ({"readOnlyHint": True}, False),
        (None, True),
        ({}, True),
        ({"readOnlyHint": False}, True),
        ({"readOnlyHint": "yes"}, True),
        ({"readOnlyHint": True, "destructiveHint": True}, True),
        ({"readOnlyHint": True, "destructiveHint": "yes"}, True),
        ({"readOnly": True}, True),
    ],
)
def test_classification_is_fail_closed_and_destructive_true_wins(metadata, expected):
    assert is_mutating(metadata) is expected


@pytest.mark.asyncio
async def test_read_only_tools_from_different_providers_can_overlap():
    catalog = NamespacedToolCatalog()
    both_started = asyncio.Event()
    release = asyncio.Event()
    started = 0

    async def read(_arguments: dict[str, object]) -> str:
        nonlocal started
        started += 1
        if started == 2:
            both_started.set()
        await release.wait()
        return "read"

    catalog.register_provider(
        "dcc-main", "dcc", [ProviderTool("read", read, {"readOnlyHint": True})]
    )
    catalog.register_provider(
        "research-main",
        "research",
        [ProviderTool("read", read, {"readOnlyHint": True})],
    )

    calls = [
        asyncio.create_task(catalog.invoke("dcc.read", {})),
        asyncio.create_task(catalog.invoke("research.read", {})),
    ]
    await asyncio.wait_for(both_started.wait(), timeout=0.5)
    release.set()
    assert await asyncio.gather(*calls) == ["read", "read"]


@pytest.mark.asyncio
async def test_mutating_and_unknown_tools_share_one_global_lock():
    catalog = NamespacedToolCatalog()
    first_started = asyncio.Event()
    release_first = asyncio.Event()
    second_started = asyncio.Event()

    async def first(_arguments: dict[str, object]) -> str:
        first_started.set()
        await release_first.wait()
        return "first"

    async def second(_arguments: dict[str, object]) -> str:
        second_started.set()
        return "second"

    catalog.register_provider("dcc-main", "dcc", [ProviderTool("write", first, {})])
    catalog.register_provider(
        "orca-main", "orca", [ProviderTool("unknown", second, None)]
    )

    first_call = asyncio.create_task(catalog.invoke("dcc.write", {}))
    await asyncio.wait_for(first_started.wait(), timeout=0.5)
    second_call = asyncio.create_task(catalog.invoke("orca.unknown", {}))
    await asyncio.sleep(0)
    assert not second_started.is_set()
    release_first.set()
    assert await asyncio.gather(first_call, second_call) == ["first", "second"]
