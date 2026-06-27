import pytest

from app.ai.museum_narrative.application.prompts import build_system_prompt
from app.ai.museum_narrative.application.use_cases import (
    GenerateNarrative,
    GenerateNarrativeInput,
    GetNarrative,
    GetNarrativeInput,
    ListNarratives,
    ListNarrativesInput,
    UpdateNarrative,
    UpdateNarrativeInput,
)
from app.ai.museum_narrative.domain.models import (
    GeneratedNarrative,
    NarrativeId,
    NarrativeType,
    ResolutionSource,
)
from app.ai.museum_narrative.domain.ports import (
    ModelUnavailable,
    NarrativeNotFound,
    UnsupportedNarrativeType,
)


class _FakeCidoc:
    def __init__(self) -> None:
        self.seen: str | None = None

    async def prepare(self, record_id: str) -> dict:
        self.seen = record_id
        return {"@graph": [{"@id": "ex:visit/" + record_id}]}


class _FakeModel:
    def __init__(self) -> None:
        self.system_prompt = ""
        self.temperature = 0.0

    async def generate(
        self, *, system_prompt: str, user_prompt: str, temperature: float
    ) -> str:
        self.system_prompt = system_prompt
        self.temperature = temperature
        return "  a narrative  "


class _FakeRepo:
    def __init__(self) -> None:
        self.stored: list[GeneratedNarrative] = []

    async def add(self, narrative: GeneratedNarrative) -> None:
        self.stored.append(narrative)

    async def save(self, narrative: GeneratedNarrative) -> None:
        self.stored = [narrative if n.id == narrative.id else n for n in self.stored]

    async def get_by_id(
        self, narrative_id: NarrativeId
    ) -> GeneratedNarrative | None:
        return next((n for n in self.stored if n.id == narrative_id), None)

    async def list_by_record(
        self, record_id: str, page: int, size: int
    ) -> tuple[list[GeneratedNarrative], int]:
        matches = [n for n in self.stored if n.record_id == record_id]
        return matches[page * size : page * size + size], len(matches)


def _use_case() -> tuple[GenerateNarrative, _FakeModel, _FakeRepo]:
    model = _FakeModel()
    repo = _FakeRepo()
    return GenerateNarrative(_FakeCidoc(), model, repo, "llama3.1:8b"), model, repo


async def test_omitted_type_defaults_to_institutional_and_persists() -> None:
    use_case, _, repo = _use_case()
    result = await use_case.execute(GenerateNarrativeInput(record_id="r1"))
    assert result.resolved_narrative_type is NarrativeType.INSTITUTIONAL
    assert result.resolution_source is ResolutionSource.DEFAULT
    assert result.narrative == "a narrative"  # stripped
    assert result.llm_model == "llama3.1:8b"
    # persisted with the generation parameters
    assert repo.stored == [result]
    assert result.id
    assert result.target_language == "pt"


async def test_explicit_type_is_used_with_request_body_source() -> None:
    use_case, model, repo = _use_case()
    result = await use_case.execute(
        GenerateNarrativeInput(
            record_id="r1", narrative_type="social_media", creativity_temperature=0.7
        )
    )
    assert result.resolved_narrative_type is NarrativeType.SOCIAL_MEDIA
    assert result.resolution_source is ResolutionSource.REQUEST_BODY
    assert result.creativity_temperature == 0.7
    assert model.temperature == 0.7
    assert "social_media" in model.system_prompt


async def test_unsupported_type_raises_and_persists_nothing() -> None:
    use_case, _, repo = _use_case()
    with pytest.raises(UnsupportedNarrativeType):
        await use_case.execute(
            GenerateNarrativeInput(record_id="r1", narrative_type="marketing_sales")
        )
    assert repo.stored == []


async def test_list_and_get_use_cases() -> None:
    repo = _FakeRepo()
    gen = GenerateNarrative(_FakeCidoc(), _FakeModel(), repo, "llama3.1:8b")
    created = await gen.execute(GenerateNarrativeInput(record_id="r1"))

    listed, total = await ListNarratives(repo).execute(
        ListNarrativesInput(record_id="r1")
    )
    assert total == 1
    assert listed == [created]

    fetched = await GetNarrative(repo).execute(
        GetNarrativeInput(record_id="r1", narrative_id=created.id)
    )
    assert fetched == created


async def test_get_missing_narrative_raises() -> None:
    with pytest.raises(NarrativeNotFound):
        await GetNarrative(_FakeRepo()).execute(
            GetNarrativeInput(record_id="r1", narrative_id="x")
        )


async def test_get_under_wrong_record_raises() -> None:
    repo = _FakeRepo()
    gen = GenerateNarrative(_FakeCidoc(), _FakeModel(), repo, "llama3.1:8b")
    created = await gen.execute(GenerateNarrativeInput(record_id="r1"))
    with pytest.raises(NarrativeNotFound):
        await GetNarrative(repo).execute(
            GetNarrativeInput(record_id="other", narrative_id=created.id)
        )


async def test_update_narrative_edits_text_and_persists() -> None:
    repo = _FakeRepo()
    gen = GenerateNarrative(_FakeCidoc(), _FakeModel(), repo, "llama3.1:8b")
    created = await gen.execute(GenerateNarrativeInput(record_id="r1"))

    updated = await UpdateNarrative(repo).execute(
        UpdateNarrativeInput(
            record_id="r1", narrative_id=created.id, narrative="  edited  "
        )
    )
    assert updated.narrative == "edited"  # stripped
    assert repo.stored[0].narrative == "edited"


async def test_update_missing_narrative_raises() -> None:
    with pytest.raises(NarrativeNotFound):
        await UpdateNarrative(_FakeRepo()).execute(
            UpdateNarrativeInput(record_id="r1", narrative_id="x", narrative="text")
        )


async def test_update_under_wrong_record_raises() -> None:
    repo = _FakeRepo()
    gen = GenerateNarrative(_FakeCidoc(), _FakeModel(), repo, "llama3.1:8b")
    created = await gen.execute(GenerateNarrativeInput(record_id="r1"))
    with pytest.raises(NarrativeNotFound):
        await UpdateNarrative(repo).execute(
            UpdateNarrativeInput(
                record_id="other", narrative_id=created.id, narrative="edited"
            )
        )
    assert repo.stored[0].narrative != "edited"


async def test_blank_model_output_is_rejected_before_persistence() -> None:
    repo = _FakeRepo()

    class _BlankModel:
        async def generate(self, *, system_prompt, user_prompt, temperature) -> str:
            return "   "

    gen = GenerateNarrative(_FakeCidoc(), _BlankModel(), repo, "llama3.1:8b")
    with pytest.raises(ModelUnavailable):
        await gen.execute(GenerateNarrativeInput(record_id="r1"))
    assert repo.stored == []


def test_each_persona_prompt_names_its_type() -> None:
    for nt in NarrativeType:
        assert nt.value in build_system_prompt(nt)
