from app.blender_bridge.journal import effective_journal, tool_mutates


def advertised_tools():
    return [
        {
            "name": "dcc.edit_mesh",
            "x_blender_hub": {"mutating": True},
        },
        {
            "name": "dcc.read_scene",
            "x_blender_hub": {"mutating": False},
        },
        {"name": "legacy.unknown"},
    ]


def test_tool_mutation_uses_hub_metadata_and_fails_closed():
    tools = advertised_tools()
    assert tool_mutates("dcc.edit_mesh", tools) is True
    assert tool_mutates("dcc.read_scene", tools) is False
    assert tool_mutates("legacy.unknown", tools) is True
    assert tool_mutates("not-advertised", tools) is True


def test_effective_journal_cannot_downgrade_mutating_tool():
    journal = effective_journal(
        "dcc.edit_mesh",
        advertised_tools(),
        {"summary": "edit", "mutation": False},
    )
    assert journal == {"summary": "edit", "mutation": True}


def test_effective_journal_marks_explicit_read_only_false_even_if_caller_claims_write():
    journal = effective_journal(
        "dcc.read_scene",
        advertised_tools(),
        {"summary": "read", "mutation": True},
    )
    assert journal == {"summary": "read", "mutation": False}


def test_effective_journal_preserves_other_metadata_and_fails_closed_without_supplied_journal():
    journal = effective_journal("legacy.unknown", advertised_tools(), None)
    assert journal == {"mutation": True}
