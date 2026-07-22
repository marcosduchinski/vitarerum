from datetime import date
from typing import Any, cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.museum_narrative.application.prompts import (
    build_system_prompt,
    build_user_prompt,
)
from app.ai.museum_narrative.application.use_cases import (
    GenerateNarrative,
    GenerateNarrativeInput,
    GetNarrative,
    GetNarrativeInput,
    ListNarrativeRevisions,
    ListNarrativeRevisionsInput,
    ListNarratives,
    ListNarrativesInput,
    PreviewNarrative,
    PreviewNarrativeInput,
    UpdateNarrative,
    UpdateNarrativeInput,
)
from app.ai.museum_narrative.domain.facts import (
    AccessFact,
    CanonicalVisitFacts,
    EvidenceGap,
    MissingFact,
    ObjectFact,
    PersonFact,
    PreparedNarrativeFacts,
)
from app.ai.museum_narrative.domain.models import (
    GeneratedNarrative,
    GeneratedNarrativeRevision,
    NarrativeFactSnapshot,
    NarrativeFactSnapshotId,
    NarrativeId,
    NarrativeType,
    ResolutionSource,
)
from app.ai.museum_narrative.domain.ports import (
    InvalidPreviewInput,
    ModelUnavailable,
    NarrativeNotFound,
    NarrativePromptUnavailable,
    NarrativePromptVersionMismatch,
    UnsupportedNarrativeType,
)
from app.ai.museum_narrative.infrastructure import cidoc_acl
from app.ai.museum_narrative.infrastructure.cidoc_acl import NarrativeFactsAdapter


def _facts(record_id: str = "r1") -> CanonicalVisitFacts:
    return CanonicalVisitFacts(
        report_subject="In-situ visit CUP-1",
        project_reference="CUP-1",
        project_title="Wolf study",
        project_purpose="Taxonomic review",
        planned_begin_date=None,
        planned_end_date=None,
        requester=PersonFact(name="Dr. Ana Ribeiro"),
        approval=MissingFact(reason="No approval was recorded in this snapshot."),
        execution=MissingFact(reason="No execution evidence was recorded."),
        evidence_gaps=[
            EvidenceGap(
                message="Não foi registado local específico da ocorrência OCC-1."
            )
        ],
        source_snapshot_id=record_id,
        source_version="2",
    )


class _FakeFacts:
    def __init__(self, facts: CanonicalVisitFacts | None = None) -> None:
        self.seen: str | None = None
        self._facts = facts
        self.cidoc_document_json = '{"@graph":[]}'
        self.cidoc_validation_report = "Conforms: True"
        self.cidoc_conforms = True

    async def prepare(self, record_id: str) -> PreparedNarrativeFacts:
        self.seen = record_id
        return PreparedNarrativeFacts(
            facts=self._facts or _facts(record_id),
            cidoc_document_json=self.cidoc_document_json,
            cidoc_validation_report=self.cidoc_validation_report,
            cidoc_conforms=self.cidoc_conforms,
        )


class _FakeModel:
    def __init__(self, text: str = "  a narrative  ") -> None:
        self.system_prompt = ""
        self.user_prompt = ""
        self.temperature = 0.0
        self._text = text

    async def generate(
        self, *, system_prompt: str, user_prompt: str, temperature: float
    ) -> str:
        self.system_prompt = system_prompt
        self.user_prompt = user_prompt
        self.temperature = temperature
        return self._text


class _FakePrompt:
    def __init__(
        self, narrative_type: NarrativeType, *, status: str = "published"
    ) -> None:
        self.version_id = f"pver-test-{narrative_type.value}-v1"
        self.version_label = f"museum-narrative-{narrative_type.value}-v1"
        self.status = status
        self.content = f"Published system prompt for {narrative_type.value} narrative."


class _FakePrompts:
    def __init__(self, *, unavailable: bool = False) -> None:
        self.seen: list[NarrativeType] = []
        self.seen_versions: list[str] = []
        self.unavailable = unavailable

    async def get_published(self, narrative_type: NarrativeType) -> _FakePrompt:
        self.seen.append(narrative_type)
        if self.unavailable:
            raise NarrativePromptUnavailable("No published prompt")
        return _FakePrompt(narrative_type)

    async def get_version(
        self, version_id: str, narrative_type: NarrativeType
    ) -> _FakePrompt:
        self.seen_versions.append(version_id)
        prompt = _FakePrompt(NarrativeType.INSTITUTIONAL, status="draft")
        prompt.version_id = version_id
        prompt.version_label = "museum-narrative-institutional-draft"
        prompt.content = "Draft system prompt."
        return prompt


class _MutablePrompts:
    def __init__(self, prompt: _FakePrompt) -> None:
        self.current = prompt

    async def get_published(self, narrative_type: NarrativeType) -> _FakePrompt:
        return self.current

    async def get_version(
        self, version_id: str, narrative_type: NarrativeType
    ) -> _FakePrompt:
        return self.current


class _MismatchedPrompts(_FakePrompts):
    async def get_version(
        self, version_id: str, narrative_type: NarrativeType
    ) -> _FakePrompt:
        raise NarrativePromptVersionMismatch("mismatch")


class _FakeRepo:
    def __init__(self) -> None:
        self.stored: list[GeneratedNarrative] = []
        self.snapshots: list[NarrativeFactSnapshot] = []
        self.revisions: list[GeneratedNarrativeRevision] = []

    async def add_facts_snapshot(self, snapshot: NarrativeFactSnapshot) -> None:
        self.snapshots.append(snapshot)

    async def get_facts_snapshot(
        self, snapshot_id: NarrativeFactSnapshotId
    ) -> NarrativeFactSnapshot | None:
        return next((s for s in self.snapshots if s.id == snapshot_id), None)

    async def add(self, narrative: GeneratedNarrative) -> None:
        self.stored.append(narrative)

    async def save(self, narrative: GeneratedNarrative) -> None:
        self.stored = [narrative if n.id == narrative.id else n for n in self.stored]

    async def add_revision(self, revision: GeneratedNarrativeRevision) -> None:
        self.revisions.append(revision)

    async def list_revisions(
        self, record_id: str, narrative_id: NarrativeId, page: int, size: int
    ) -> tuple[list[GeneratedNarrativeRevision], int] | None:
        narrative = await self.get_by_id(narrative_id)
        if narrative is None or narrative.record_id != record_id:
            return None
        matches = [r for r in self.revisions if r.narrative_id == narrative_id]
        matches.sort(key=lambda revision: revision.created_at)
        return matches[page * size : page * size + size], len(matches)

    async def get_by_id(self, narrative_id: NarrativeId) -> GeneratedNarrative | None:
        return next((n for n in self.stored if n.id == narrative_id), None)

    async def list_by_record(
        self, record_id: str, page: int, size: int
    ) -> tuple[list[GeneratedNarrative], int]:
        matches = [n for n in self.stored if n.record_id == record_id]
        return matches[page * size : page * size + size], len(matches)


def _use_case() -> tuple[GenerateNarrative, _FakeModel, _FakeRepo]:
    model = _FakeModel()
    repo = _FakeRepo()
    return (
        GenerateNarrative(_FakeFacts(), _FakePrompts(), model, repo, "llama3.1:8b"),
        model,
        repo,
    )


def _use_case_with_facts(
    facts: CanonicalVisitFacts, model_text: str = "  a narrative  "
) -> tuple[GenerateNarrative, _FakeModel, _FakeRepo]:
    model = _FakeModel(model_text)
    repo = _FakeRepo()
    return (
        GenerateNarrative(
            _FakeFacts(facts), _FakePrompts(), model, repo, "llama3.1:8b"
        ),
        model,
        repo,
    )


async def test_omitted_type_defaults_to_institutional_and_persists() -> None:
    use_case, _, repo = _use_case()
    result = await use_case.execute(GenerateNarrativeInput(record_id="r1"))
    assert result.resolved_narrative_type is NarrativeType.INSTITUTIONAL
    assert result.resolution_source is ResolutionSource.DEFAULT
    assert result.narrative == "a narrative"  # stripped
    assert result.llm_model == "llama3.1:8b"
    # persisted with the generation parameters
    assert repo.stored == [result]
    assert len(repo.snapshots) == 1
    assert result.facts_snapshot_id == repo.snapshots[0].id
    assert result.prompt_version_id == "pver-test-institutional-v1"
    assert result.prompt_version == "museum-narrative-institutional-v1"
    assert result.prompt_version == repo.snapshots[0].prompt_version
    assert result.model_response_hash
    assert result.id
    assert result.target_language == "pt"


async def test_fact_snapshot_freezes_payload_used_for_generation() -> None:
    initial_facts = _facts("r1")
    use_case, _, repo = _use_case_with_facts(initial_facts)

    result = await use_case.execute(GenerateNarrativeInput(record_id="r1"))
    assert result.facts_snapshot_id is not None
    snapshot = await repo.get_facts_snapshot(result.facts_snapshot_id)

    initial_facts.evidence_gaps.append(
        EvidenceGap(message="later builder/source change")
    )
    assert snapshot is not None
    assert "Wolf study" in snapshot.payload_json
    assert "later builder/source change" not in snapshot.payload_json


async def test_generation_uses_published_prompt_registry_output() -> None:
    use_case, model, repo = _use_case()

    result = await use_case.execute(
        GenerateNarrativeInput(record_id="r1", narrative_type="scientific")
    )

    assert model.system_prompt == "Published system prompt for scientific narrative."
    assert result.prompt_version_id == "pver-test-scientific-v1"
    assert result.prompt_version == "museum-narrative-scientific-v1"
    assert repo.snapshots[0].prompt_version == "museum-narrative-scientific-v1"


async def test_preview_uses_prompt_version_without_persisting_narrative() -> None:
    facts = _FakeFacts()
    prompts = _FakePrompts()
    model = _FakeModel(" preview narrative ")
    repo = _FakeRepo()
    use_case = PreviewNarrative(facts, prompts, model, "llama3.1:8b")

    result = await use_case.execute(
        PreviewNarrativeInput(
            record_id="r1",
            prompt_version_id="draft-version-1",
            narrative_type="institutional",
            creativity_temperature=None,
        )
    )

    assert facts.seen == "r1"
    assert prompts.seen_versions == ["draft-version-1"]
    assert model.system_prompt == "Draft system prompt."
    assert model.temperature == 0.3
    assert result.narrative == "preview narrative"
    assert result.prompt_version_id == "draft-version-1"
    assert result.prompt_version == "museum-narrative-institutional-draft"
    assert result.prompt_status == "draft"
    assert result.prompt_source == "version"
    assert result.llm_model == "llama3.1:8b"
    assert result.model_response_hash
    assert repo.stored == []
    assert repo.snapshots == []


async def test_preview_uses_ad_hoc_content_without_persisting() -> None:
    facts = _FakeFacts()
    prompts = _FakePrompts()
    model = _FakeModel(" preview narrative ")
    repo = _FakeRepo()
    use_case = PreviewNarrative(facts, prompts, model, "llama3.1:8b")

    result = await use_case.execute(
        PreviewNarrativeInput(
            record_id="r1",
            prompt_version_id=None,
            content="  Ad-hoc system prompt.  ",
            narrative_type="institutional",
            creativity_temperature=0.7,
        )
    )

    assert facts.seen == "r1"
    assert prompts.seen_versions == []
    assert model.system_prompt == "Ad-hoc system prompt."
    assert model.temperature == 0.7
    assert result.narrative == "preview narrative"
    assert result.prompt_version_id is None
    assert result.prompt_version is None
    assert result.prompt_status is None
    assert result.prompt_source == "adhoc"
    assert result.llm_model == "llama3.1:8b"
    assert repo.stored == []
    assert repo.snapshots == []


@pytest.mark.parametrize(
    "input_data",
    [
        PreviewNarrativeInput(record_id="r1", prompt_version_id=None, content=None),
        PreviewNarrativeInput(
            record_id="r1",
            prompt_version_id="draft-version-1",
            content="Ad-hoc system prompt.",
            narrative_type="institutional",
        ),
        PreviewNarrativeInput(
            record_id="r1",
            prompt_version_id=None,
            content="Ad-hoc system prompt.",
            narrative_type=None,
        ),
        PreviewNarrativeInput(
            record_id="r1",
            prompt_version_id=None,
            content="",
            narrative_type="institutional",
        ),
        PreviewNarrativeInput(
            record_id="r1",
            prompt_version_id=None,
            content="   ",
            narrative_type="institutional",
        ),
    ],
)
async def test_preview_rejects_invalid_prompt_source_combinations(
    input_data: PreviewNarrativeInput,
) -> None:
    facts = _FakeFacts()
    model = _FakeModel()
    use_case = PreviewNarrative(facts, _FakePrompts(), model, "llama3.1:8b")

    with pytest.raises(InvalidPreviewInput):
        await use_case.execute(input_data)

    assert facts.seen is None
    assert model.system_prompt == ""


async def test_preview_rejects_prompt_version_for_another_narrative_type() -> None:
    facts = _FakeFacts()
    model = _FakeModel()
    use_case = PreviewNarrative(facts, _MismatchedPrompts(), model, "llama3.1:8b")

    with pytest.raises(NarrativePromptVersionMismatch):
        await use_case.execute(
            PreviewNarrativeInput(
                record_id="r1",
                prompt_version_id="social-media-draft",
                narrative_type="institutional",
            )
        )

    assert facts.seen is None
    assert model.system_prompt == ""


async def test_existing_narrative_keeps_prompt_version_after_new_publish() -> None:
    prompts = _MutablePrompts(_FakePrompt(NarrativeType.INSTITUTIONAL))
    model = _FakeModel(" first narrative ")
    repo = _FakeRepo()
    use_case = GenerateNarrative(_FakeFacts(), prompts, model, repo, "llama3.1:8b")

    first = await use_case.execute(GenerateNarrativeInput(record_id="r1"))
    prompts.current = _FakePrompt(NarrativeType.SCIENTIFIC)
    second = await use_case.execute(GenerateNarrativeInput(record_id="r2"))

    assert first.prompt_version_id == "pver-test-institutional-v1"
    assert first.prompt_version == "museum-narrative-institutional-v1"
    assert second.prompt_version_id == "pver-test-scientific-v1"
    assert second.prompt_version == "museum-narrative-scientific-v1"
    assert repo.stored[0].prompt_version_id == "pver-test-institutional-v1"
    assert repo.stored[0].prompt_version == "museum-narrative-institutional-v1"


async def test_missing_published_prompt_fails_without_hardcoded_fallback() -> None:
    facts = _FakeFacts()
    repo = _FakeRepo()
    model = _FakeModel()
    use_case = GenerateNarrative(
        facts,
        _FakePrompts(unavailable=True),
        model,
        repo,
        "llama3.1:8b",
    )

    with pytest.raises(NarrativePromptUnavailable):
        await use_case.execute(GenerateNarrativeInput(record_id="r1"))

    assert facts.seen is None
    assert model.system_prompt == ""
    assert repo.snapshots == []
    assert repo.stored == []


async def test_fact_snapshot_freezes_cidoc_gate_output_used_for_generation() -> None:
    facts = _FakeFacts()
    model = _FakeModel()
    repo = _FakeRepo()
    use_case = GenerateNarrative(facts, _FakePrompts(), model, repo, "llama3.1:8b")

    result = await use_case.execute(GenerateNarrativeInput(record_id="r1"))
    assert result.facts_snapshot_id is not None
    snapshot = await repo.get_facts_snapshot(result.facts_snapshot_id)

    facts.cidoc_document_json = '{"@graph":[{"later":"mapping change"}]}'
    facts.cidoc_validation_report = "later SHACL report"
    facts.cidoc_conforms = False

    assert snapshot is not None
    assert snapshot.cidoc_document_json == '{"@graph":[]}'
    assert snapshot.cidoc_validation_report == "Conforms: True"
    assert snapshot.cidoc_conforms is True


async def test_narrative_with_invented_date_is_marked_for_review() -> None:
    use_case, _, _ = _use_case_with_facts(
        _facts("r1"),
        model_text="The visit produced a result on 2027-05-01.",
    )

    result = await use_case.execute(GenerateNarrativeInput(record_id="r1"))

    assert result.validation_conforms is False
    assert result.validation_findings[0].code.value == "invented_date"
    assert result.validation_findings[0].evidence == "2027-05-01"


async def test_planned_date_as_execution_is_marked_for_review() -> None:
    facts = CanonicalVisitFacts(
        report_subject="In-situ visit CUP-1",
        project_reference="CUP-1",
        project_title="Wolf study",
        project_purpose="Taxonomic review",
        planned_begin_date=date(2026, 1, 10),
        planned_end_date=date(2026, 1, 11),
        requester=PersonFact(name="Dr. Ana Ribeiro"),
        approval=MissingFact(reason="No approval was recorded."),
        execution=MissingFact(reason="No execution evidence was recorded."),
        source_snapshot_id="r1",
        source_version="2",
    )
    use_case, _, _ = _use_case_with_facts(
        facts,
        model_text="A visita ocorreu em 2026-01-10.",
    )

    result = await use_case.execute(GenerateNarrativeInput(record_id="r1"))

    assert result.validation_conforms is False
    assert any(
        finding.code.value == "planned_date_as_executed"
        for finding in result.validation_findings
    )


async def test_date_inside_planned_interval_is_allowed() -> None:
    facts = CanonicalVisitFacts(
        report_subject="In-situ visit CUP-1",
        project_reference="CUP-1",
        project_title="Wolf study",
        project_purpose="Taxonomic review",
        planned_begin_date=date(2026, 6, 1),
        planned_end_date=date(2026, 6, 3),
        requester=PersonFact(name="Dr. Ana Ribeiro"),
        approval=MissingFact(reason="No approval was recorded."),
        execution=MissingFact(reason="No execution evidence was recorded."),
        source_snapshot_id="r1",
        source_version="2",
    )
    use_case, _, _ = _use_case_with_facts(
        facts,
        model_text="No segundo dia planeado, 2026-06-02, a equipa reviu os dados.",
    )

    result = await use_case.execute(GenerateNarrativeInput(record_id="r1"))

    assert result.validation_conforms is True
    assert result.validation_findings == []


async def test_invented_person_object_and_place_are_marked_for_review() -> None:
    facts = CanonicalVisitFacts(
        report_subject="In-situ visit CUP-1",
        project_reference="CUP-1",
        project_title="Wolf study",
        project_purpose="Taxonomic review",
        planned_begin_date=None,
        planned_end_date=None,
        requester=PersonFact(name="Dr. Ana Ribeiro"),
        approval=MissingFact(reason="No approval was recorded."),
        execution=MissingFact(reason="No execution evidence was recorded."),
        objects=[
            ObjectFact(
                source_id="INV-001",
                label="Iberian wolf",
                description=None,
                position=0,
            )
        ],
        access_logs=[
            AccessFact(
                source_id="LOG-1",
                description=None,
                related_object_source_id="INV-001",
                number_of_objects=1,
                added_at=None,
                added_by=None,
                conclusion_at=None,
                curator=None,
                position=0,
            )
        ],
        source_snapshot_id="r1",
        source_version="2",
    )
    use_case, _, _ = _use_case_with_facts(
        facts,
        model_text=("Dr. Miguel Silva examined INV-999 in Gallery B during the visit."),
    )

    result = await use_case.execute(GenerateNarrativeInput(record_id="r1"))

    codes = {finding.code.value for finding in result.validation_findings}
    assert result.validation_conforms is False
    assert "invented_person" in codes
    assert "invented_object" in codes
    assert "invented_place" in codes


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


async def test_user_prompt_receives_canonical_facts_and_declared_absence() -> None:
    use_case, model, _ = _use_case()
    await use_case.execute(GenerateNarrativeInput(record_id="r1"))
    assert "[CANONICAL VISIT FACTS]" in model.user_prompt
    assert "CIDOC-CRM Validated Graph" not in model.user_prompt
    assert (
        "Não foi registado local específico da ocorrência OCC-1." in model.user_prompt
    )
    assert "crm:" not in model.user_prompt
    assert "http://www.cidoc-crm.org" not in model.user_prompt
    assert "ex:visit" not in model.user_prompt


async def test_unsupported_type_raises_and_persists_nothing() -> None:
    use_case, _, repo = _use_case()
    with pytest.raises(UnsupportedNarrativeType):
        await use_case.execute(
            GenerateNarrativeInput(record_id="r1", narrative_type="marketing_sales")
        )
    assert repo.stored == []


async def test_list_and_get_use_cases() -> None:
    repo = _FakeRepo()
    gen = GenerateNarrative(
        _FakeFacts(), _FakePrompts(), _FakeModel(), repo, "llama3.1:8b"
    )
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
    gen = GenerateNarrative(
        _FakeFacts(), _FakePrompts(), _FakeModel(), repo, "llama3.1:8b"
    )
    created = await gen.execute(GenerateNarrativeInput(record_id="r1"))
    with pytest.raises(NarrativeNotFound):
        await GetNarrative(repo).execute(
            GetNarrativeInput(record_id="other", narrative_id=created.id)
        )


async def test_update_narrative_edits_text_and_persists() -> None:
    repo = _FakeRepo()
    gen = GenerateNarrative(
        _FakeFacts(), _FakePrompts(), _FakeModel(), repo, "llama3.1:8b"
    )
    created = await gen.execute(GenerateNarrativeInput(record_id="r1"))

    updated = await UpdateNarrative(repo).execute(
        UpdateNarrativeInput(
            record_id="r1",
            narrative_id=created.id,
            narrative="  edited  ",
            edited_by="perm-staff",
        )
    )
    assert updated.narrative == "edited"  # stripped
    assert repo.stored[0].narrative == "edited"
    assert len(repo.revisions) == 1
    assert repo.revisions[0].previous_narrative == "a narrative"
    assert repo.revisions[0].revised_narrative == "edited"
    assert repo.revisions[0].edited_by == "perm-staff"


async def test_list_revisions_empty_for_never_edited_narrative() -> None:
    repo = _FakeRepo()
    gen = GenerateNarrative(
        _FakeFacts(), _FakePrompts(), _FakeModel(), repo, "llama3.1:8b"
    )
    created = await gen.execute(GenerateNarrativeInput(record_id="r1"))

    revisions, total = await ListNarrativeRevisions(repo).execute(
        ListNarrativeRevisionsInput(record_id="r1", narrative_id=created.id)
    )

    assert revisions == []
    assert total == 0


async def test_list_revisions_returns_chronological_editorial_history() -> None:
    repo = _FakeRepo()
    gen = GenerateNarrative(
        _FakeFacts(), _FakePrompts(), _FakeModel(), repo, "llama3.1:8b"
    )
    created = await gen.execute(GenerateNarrativeInput(record_id="r1"))
    update = UpdateNarrative(repo)

    await update.execute(
        UpdateNarrativeInput(
            record_id="r1",
            narrative_id=created.id,
            narrative="first edit",
            edited_by="perm-a",
        )
    )
    await update.execute(
        UpdateNarrativeInput(
            record_id="r1",
            narrative_id=created.id,
            narrative="second edit",
            edited_by="perm-b",
        )
    )

    revisions, total = await ListNarrativeRevisions(repo).execute(
        ListNarrativeRevisionsInput(record_id="r1", narrative_id=created.id)
    )

    assert total == 2
    assert [revision.previous_narrative for revision in revisions] == [
        "a narrative",
        "first edit",
    ]
    assert [revision.revised_narrative for revision in revisions] == [
        "first edit",
        "second edit",
    ]
    assert [revision.edited_by for revision in revisions] == ["perm-a", "perm-b"]


async def test_update_missing_narrative_raises() -> None:
    with pytest.raises(NarrativeNotFound):
        await UpdateNarrative(_FakeRepo()).execute(
            UpdateNarrativeInput(
                record_id="r1",
                narrative_id="x",
                narrative="text",
                edited_by="perm-staff",
            )
        )


async def test_update_under_wrong_record_raises() -> None:
    repo = _FakeRepo()
    gen = GenerateNarrative(
        _FakeFacts(), _FakePrompts(), _FakeModel(), repo, "llama3.1:8b"
    )
    created = await gen.execute(GenerateNarrativeInput(record_id="r1"))
    with pytest.raises(NarrativeNotFound):
        await UpdateNarrative(repo).execute(
            UpdateNarrativeInput(
                record_id="other",
                narrative_id=created.id,
                narrative="edited",
                edited_by="perm-staff",
            )
        )
    assert repo.stored[0].narrative != "edited"


async def test_list_revisions_under_wrong_record_raises() -> None:
    repo = _FakeRepo()
    gen = GenerateNarrative(
        _FakeFacts(), _FakePrompts(), _FakeModel(), repo, "llama3.1:8b"
    )
    created = await gen.execute(GenerateNarrativeInput(record_id="r1"))
    await UpdateNarrative(repo).execute(
        UpdateNarrativeInput(
            record_id="r1",
            narrative_id=created.id,
            narrative="edited",
            edited_by="perm-staff",
        )
    )

    with pytest.raises(NarrativeNotFound):
        await ListNarrativeRevisions(repo).execute(
            ListNarrativeRevisionsInput(record_id="other", narrative_id=created.id)
        )


async def test_blank_model_output_is_rejected_before_persistence() -> None:
    repo = _FakeRepo()

    class _BlankModel:
        async def generate(
            self, *, system_prompt: str, user_prompt: str, temperature: float
        ) -> str:
            return "   "

    gen = GenerateNarrative(
        _FakeFacts(), _FakePrompts(), _BlankModel(), repo, "llama3.1:8b"
    )
    with pytest.raises(ModelUnavailable):
        await gen.execute(GenerateNarrativeInput(record_id="r1"))
    assert repo.stored == []


async def test_facts_adapter_validates_cidoc_before_facts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    compact_doc = {"@context": {"ex": "http://example.org/"}, "@graph": []}
    calls: list[str] = []

    async def build(_session: AsyncSession, record_id: str) -> dict[str, Any]:
        calls.append(record_id)
        return compact_doc

    async def view(_session: AsyncSession, record_id: str) -> object:
        assert record_id == "r1"
        return type(
            "RecordView",
            (),
            {
                "id": "r1",
                "code": "CUP-1",
                "sourceProjectTitle": "Wolf study",
                "sourceProjectPurpose": "Taxonomic review",
                "plannedBeginDate": None,
                "plannedEndDate": None,
                "visitBeginDate": None,
                "visitEndDate": None,
                "visitorName": "Dr. Ana Ribeiro",
                "approvedAt": None,
                "approvedBy": None,
                "approvalNote": None,
                "executionEvidenceType": None,
                "executionOccurredAt": None,
                "executionRecordedBy": None,
                "executionEvidenceGaps": [],
                "requestedObjects": [],
                "inSituOccurrences": [],
                "inSituLogs": [],
                "inSituPublications": [],
                "recordSchemaVersion": 2,
            },
        )()

    def validate(doc: dict[str, Any]) -> tuple[bool, str]:
        assert doc is compact_doc
        return True, "ok"

    monkeypatch.setattr(cidoc_acl, "build_in_situ_visit_cidoc", build)
    monkeypatch.setattr(cidoc_acl, "get_in_situ_visit_record_view", view)
    monkeypatch.setattr(cidoc_acl, "validate_cidoc", validate)

    result = await NarrativeFactsAdapter(cast(AsyncSession, object())).prepare("r1")

    assert result.facts.source_snapshot_id == "r1"
    assert result.facts.project_reference == "CUP-1"
    assert result.cidoc_document_json == (
        '{"@context": {"ex": "http://example.org/"}, "@graph": []}'
    )
    assert result.cidoc_validation_report == "ok"
    assert result.cidoc_conforms is True
    assert calls == ["r1"]


def test_each_persona_prompt_names_its_type() -> None:
    for nt in NarrativeType:
        assert nt.value in build_system_prompt(nt)


def test_user_prompt_labels_compact_declared_data() -> None:
    prompt = build_user_prompt(_facts(), "pt")
    assert "[CANONICAL VISIT FACTS]" in prompt
    assert "CIDOC-CRM Validated Graph" not in prompt
    assert '"evidence_gaps"' in prompt
    assert "crm:" not in prompt
