from app.fusion_cad.diff import minimal_semantic_diff


def test_minimal_semantic_diff_contains_only_hashes_counts_and_opaque_refs():
    before = {
        "structural_hash": "sha256:before",
        "counts": {"bodies": 1, "sketches": 0},
        "refs": ["ref_body_existing"],
        "native_token": "must-not-leak",
    }
    after = {
        "structural_hash": "sha256:after",
        "counts": {"bodies": 1, "sketches": 1},
        "refs": ["ref_body_existing", "ref_sketch_preview"],
        "native_token": "must-not-leak-either",
    }
    assert minimal_semantic_diff(before, after) == {
        "before": {
            "structural_hash": "sha256:before",
            "counts": {"bodies": 1, "sketches": 0},
        },
        "after": {
            "structural_hash": "sha256:after",
            "counts": {"bodies": 1, "sketches": 1},
        },
        "counts": {"bodies": 0, "sketches": 1},
        "refs": {"added": ["ref_sketch_preview"], "removed": []},
    }
