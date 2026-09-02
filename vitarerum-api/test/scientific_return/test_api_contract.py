from app.main import app


def test_openapi_excludes_bench_and_keeps_operational_scientific_return() -> None:
    openapi_paths = app.openapi()["paths"]
    paths = set(openapi_paths)

    assert not any("/scientific-return/test-" in path for path in paths)
    assert not any("/scientific-return/internal/test-" in path for path in paths)

    required_fragments = (
        "/watch",
        "/runs",
        "/candidates",
        "/decisions",
        "/investigations",
        "/full-agentic-investigations",
        "/knowledge-items",
        "/metrics",
    )
    for fragment in required_fragments:
        assert any(fragment in path for path in paths), fragment

    assert "/api/v1/scientific-return/watches/lookup" in paths
    assert (
        "/api/v1/scientific-return/knowledge-items/{item_id}/history" in paths
    )

    list_operation = openapi_paths["/api/v1/scientific-return/knowledge-items"]["get"]
    parameter_names = {parameter["name"] for parameter in list_operation["parameters"]}
    assert {"status", "kind", "q", "page", "size"} <= parameter_names
    # The superseded citation-only parameter stays for older clients.
    assert "inventoryNumber" in parameter_names


def test_openapi_removes_shadow_generation_but_keeps_reader_provenance() -> None:
    paths = app.openapi()["paths"]
    history_path = (
        "/api/v1/scientific-return/candidates/{candidate_id}/agent-analyses"
    )
    history = paths[history_path]

    assert "get" in history
    assert "post" not in history
    assert (
        "post"
        in paths["/api/v1/scientific-return/agent-analyses/{analysis_id}/feedback"]
    )
