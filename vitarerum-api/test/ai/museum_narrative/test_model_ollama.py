from app.ai.museum_narrative.infrastructure.model_ollama import (
    _is_ollama_response_error,
)


def test_identifies_ollama_response_error() -> None:
    response_error = type(
        "ResponseError",
        (Exception,),
        {"__module__": "ollama._types"},
    )

    assert _is_ollama_response_error(response_error("model unavailable"))


def test_does_not_identify_other_response_error() -> None:
    response_error = type(
        "ResponseError",
        (Exception,),
        {"__module__": "some_other_client"},
    )

    assert not _is_ollama_response_error(response_error("different client"))
