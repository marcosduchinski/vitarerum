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
