from app.main import app


def test_openapi_excludes_bench_and_keeps_operational_scientific_return() -> None:
    paths = set(app.openapi()["paths"])

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
