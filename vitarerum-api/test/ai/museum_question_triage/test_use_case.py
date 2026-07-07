from datetime import UTC, datetime

import pytest

from app.ai.museum_question_triage.application.use_cases import (
    GetLatestTriage,
    GetLatestTriageInput,
    TriageMuseumQuestion,
    TriageMuseumQuestionInput,
)
from app.ai.museum_question_triage.domain.models import (
    MentionedObject,
    MessageTriage,
    ObjectHitView,
    QuestionView,
    TriageClassification,
    TriageId,
    TriageVerdict,
)
from app.ai.museum_question_triage.domain.ports import (
    ModelUnavailable,
    QuestionNotFound,
)
from app.identity.public import Actor, GroupName, PermissionId

_STAFF = Actor(
    id=PermissionId("perm-staff"), group=GroupName.CURATORIAL, email="s@museum.pt"
)

_QUESTION = QuestionView(
    id="q1",
    subject="Visit request",
    message="I would like to visit and study the meteorite collection.",
    requester_email="researcher@uni.pt",
    status="SUBMITTED",
)


class _FakeMuseumQuestion:
    def __init__(self, question: QuestionView | None = _QUESTION) -> None:
        self._question = question

    async def get_summary(self, question_id: str) -> QuestionView | None:
        return self._question


class _FakeModel:
    def __init__(
        self,
        *,
        is_visit_related: bool = True,
        mentioned_objects: list[MentionedObject] | None = None,
        reply: str = "Thanks, but this is out of scope.",
        classify_error: Exception | None = None,
    ) -> None:
        self._is_visit_related = is_visit_related
        self._mentioned_objects = mentioned_objects or []
        self._reply = reply
        self._classify_error = classify_error
        self.classify_calls: list[str] = []
        self.reply_calls: list[str] = []

    async def classify(self, message: str) -> TriageClassification:
        self.classify_calls.append(message)
        if self._classify_error is not None:
            raise self._classify_error
        return TriageClassification(
            is_visit_related=self._is_visit_related,
            mentioned_objects=self._mentioned_objects,
        )

    async def draft_out_of_scope_reply(self, message: str) -> str:
        self.reply_calls.append(message)
        return self._reply


class _FakeObjectSearch:
    def __init__(
        self, hits_by_query: dict[str, list[ObjectHitView]] | None = None
    ) -> None:
        self._hits_by_query = hits_by_query or {}
        self.calls: list[tuple[Actor, str, int]] = []

    async def search(
        self, caller: Actor, query: str, limit: int
    ) -> list[ObjectHitView]:
        self.calls.append((caller, query, limit))
        return self._hits_by_query.get(query, [])


class _FakeRepo:
    def __init__(self) -> None:
        self.stored: list[MessageTriage] = []

    async def add(self, triage: MessageTriage) -> None:
        self.stored.append(triage)

    async def get_latest_by_question(
        self, question_id: str
    ) -> MessageTriage | None:
        matches = [t for t in self.stored if t.question_id == question_id]
        matches.sort(key=lambda t: t.created_at, reverse=True)
        return matches[0] if matches else None


def _use_case(
    *,
    museum_question: _FakeMuseumQuestion | None = None,
    model: _FakeModel | None = None,
    object_search: _FakeObjectSearch | None = None,
    repo: _FakeRepo | None = None,
) -> tuple[TriageMuseumQuestion, _FakeModel, _FakeObjectSearch, _FakeRepo]:
    mq = museum_question or _FakeMuseumQuestion()
    model_ = model or _FakeModel()
    search = object_search or _FakeObjectSearch()
    repository = repo or _FakeRepo()
    return (
        TriageMuseumQuestion(mq, model_, search, repository, "llama3.1:8b"),
        model_,
        search,
        repository,
    )


async def test_out_of_scope_drafts_reply_and_skips_search() -> None:
    use_case, model, object_search, repo = _use_case(
        model=_FakeModel(is_visit_related=False)
    )
    result = await use_case.execute(
        TriageMuseumQuestionInput(question_id="q1", caller=_STAFF)
    )
    assert result.verdict is TriageVerdict.OUT_OF_SCOPE
    assert result.suggested_reply == "Thanks, but this is out of scope."
    assert result.object_matches == []
    assert object_search.calls == []
    assert model.reply_calls == [_QUESTION.message]
    assert repo.stored == [result]


async def test_in_scope_with_objects_searches_each_language() -> None:
    pt_hit = ObjectHitView(
        collection_id="c1",
        collection_name="Meteorites",
        file_name="rows.xlsx",
        highlight="<b>Allende</b>",
    )
    use_case, _model, object_search, _repo = _use_case(
        model=_FakeModel(
            is_visit_related=True,
            mentioned_objects=[
                MentionedObject(
                    english="Allende meteorite", portuguese="Meteorito Allende"
                ),
                MentionedObject(english="Ghost object", portuguese="Objeto fantasma"),
            ],
        ),
        object_search=_FakeObjectSearch({"Meteorito Allende": [pt_hit]}),
    )
    result = await use_case.execute(
        TriageMuseumQuestionInput(question_id="q1", caller=_STAFF)
    )
    assert result.verdict is TriageVerdict.IN_SCOPE
    assert result.suggested_reply is None
    assert [(m.english, m.portuguese) for m in result.object_matches] == [
        ("Allende meteorite", "Meteorito Allende"),
        ("Ghost object", "Objeto fantasma"),
    ]
    assert result.object_matches[0].hits == [pt_hit]
    assert result.object_matches[1].hits == []  # not found in catalogue

    # Portuguese searched first, then English, for each of the two objects.
    assert object_search.calls == [
        (_STAFF, "Meteorito Allende", 5),
        (_STAFF, "Allende meteorite", 5),
        (_STAFF, "Objeto fantasma", 5),
        (_STAFF, "Ghost object", 5),
    ]


async def test_search_skips_english_when_identical_to_portuguese() -> None:
    use_case, _model, object_search, _repo = _use_case(
        model=_FakeModel(
            is_visit_related=True,
            mentioned_objects=[
                MentionedObject(english="Allende", portuguese="Allende"),
            ],
        )
    )
    await use_case.execute(TriageMuseumQuestionInput(question_id="q1", caller=_STAFF))
    assert object_search.calls == [(_STAFF, "Allende", 5)]


async def test_hits_from_both_languages_are_merged_and_deduplicated() -> None:
    shared_hit = ObjectHitView(
        collection_id="c1",
        collection_name="Meteorites",
        file_name="rows.xlsx",
        highlight="<b>Allende</b>",
    )
    english_only_hit = ObjectHitView(
        collection_id="c2",
        collection_name="Meteorites",
        file_name="other.xlsx",
        highlight="<b>Allende</b> chondrite",
    )
    use_case, _model, _object_search, _repo = _use_case(
        model=_FakeModel(
            is_visit_related=True,
            mentioned_objects=[
                MentionedObject(
                    english="Allende meteorite", portuguese="Meteorito Allende"
                ),
            ],
        ),
        object_search=_FakeObjectSearch(
            {
                "Meteorito Allende": [shared_hit],
                "Allende meteorite": [shared_hit, english_only_hit],
            }
        ),
    )
    result = await use_case.execute(
        TriageMuseumQuestionInput(question_id="q1", caller=_STAFF)
    )
    assert result.object_matches[0].hits == [shared_hit, english_only_hit]


async def test_distinct_rows_in_the_same_file_are_not_deduplicated_away() -> None:
    # Two different rows of the same spreadsheet: the Portuguese search
    # finds one, the English search finds another. Same collection_id/
    # file_name, but different highlight — both must be kept.
    row_five = ObjectHitView(
        collection_id="c1",
        collection_name="Zoology",
        file_name="zoology.xlsx",
        highlight="row 5: <b>baleia</b> azul",
    )
    row_twelve = ObjectHitView(
        collection_id="c1",
        collection_name="Zoology",
        file_name="zoology.xlsx",
        highlight="row 12: blue <b>whale</b>",
    )
    use_case, _model, _object_search, _repo = _use_case(
        model=_FakeModel(
            is_visit_related=True,
            mentioned_objects=[
                MentionedObject(english="Blue whale", portuguese="Baleia azul"),
            ],
        ),
        object_search=_FakeObjectSearch(
            {"Baleia azul": [row_five], "Blue whale": [row_twelve]}
        ),
    )
    result = await use_case.execute(
        TriageMuseumQuestionInput(question_id="q1", caller=_STAFF)
    )
    assert result.object_matches[0].hits == [row_five, row_twelve]


async def test_mentioned_objects_are_trimmed_deduplicated_and_blanks_dropped() -> None:
    use_case, _model, object_search, repo = _use_case(
        model=_FakeModel(
            is_visit_related=True,
            mentioned_objects=[
                MentionedObject(
                    english="  Allende meteorite ", portuguese="  Meteorito Allende "
                ),
                MentionedObject(
                    english="Allende meteorite", portuguese="Meteorito Allende"
                ),
                MentionedObject(
                    english="ALLENDE METEORITE", portuguese="METEORITO ALLENDE"
                ),
                MentionedObject(english="", portuguese=""),
                MentionedObject(english="   ", portuguese="   "),
                MentionedObject(english="Ghost object", portuguese="Ghost object"),
            ],
        )
    )
    result = await use_case.execute(
        TriageMuseumQuestionInput(question_id="q1", caller=_STAFF)
    )
    assert result.mentioned_objects == [
        MentionedObject(english="Allende meteorite", portuguese="Meteorito Allende"),
        MentionedObject(english="Ghost object", portuguese="Ghost object"),
    ]
    assert [(m.english, m.portuguese) for m in result.object_matches] == [
        ("Allende meteorite", "Meteorito Allende"),
        ("Ghost object", "Ghost object"),
    ]
    # first object: 2 searches (distinct pt/en); second: 1 (identical pt/en)
    assert len(object_search.calls) == 3
    assert repo.stored[0].mentioned_objects == result.mentioned_objects


async def test_same_portuguese_but_different_english_are_kept_distinct() -> None:
    # An imprecise translation could give two different objects the same
    # Portuguese name — deduping on Portuguese alone would silently drop one.
    use_case, _model, _object_search, _repo = _use_case(
        model=_FakeModel(
            is_visit_related=True,
            mentioned_objects=[
                MentionedObject(english="Blue whale", portuguese="Baleia"),
                MentionedObject(english="Right whale", portuguese="Baleia"),
            ],
        )
    )
    result = await use_case.execute(
        TriageMuseumQuestionInput(question_id="q1", caller=_STAFF)
    )
    assert result.mentioned_objects == [
        MentionedObject(english="Blue whale", portuguese="Baleia"),
        MentionedObject(english="Right whale", portuguese="Baleia"),
    ]


async def test_blank_language_falls_back_to_the_other() -> None:
    use_case, _model, _object_search, _repo = _use_case(
        model=_FakeModel(
            is_visit_related=True,
            mentioned_objects=[MentionedObject(english="", portuguese="Baleia")],
        )
    )
    result = await use_case.execute(
        TriageMuseumQuestionInput(question_id="q1", caller=_STAFF)
    )
    assert result.mentioned_objects == [
        MentionedObject(english="Baleia", portuguese="Baleia")
    ]


async def test_in_scope_without_objects_skips_search() -> None:
    use_case, _model, object_search, _repo = _use_case(
        model=_FakeModel(is_visit_related=True, mentioned_objects=[])
    )
    result = await use_case.execute(
        TriageMuseumQuestionInput(question_id="q1", caller=_STAFF)
    )
    assert result.verdict is TriageVerdict.IN_SCOPE
    assert result.object_matches == []
    assert object_search.calls == []


async def test_object_queries_are_capped_at_three() -> None:
    use_case, _model, object_search, _repo = _use_case(
        model=_FakeModel(
            is_visit_related=True,
            mentioned_objects=[
                MentionedObject(english=x, portuguese=x) for x in ["a", "b", "c", "d"]
            ],
        )
    )
    result = await use_case.execute(
        TriageMuseumQuestionInput(question_id="q1", caller=_STAFF)
    )
    assert len(result.object_matches) == 3
    assert len(object_search.calls) == 3  # english == portuguese, 1 search each


async def test_missing_question_raises() -> None:
    use_case, *_ = _use_case(museum_question=_FakeMuseumQuestion(question=None))
    with pytest.raises(QuestionNotFound):
        await use_case.execute(
            TriageMuseumQuestionInput(question_id="missing", caller=_STAFF)
        )


async def test_model_unavailable_propagates() -> None:
    use_case, *_ = _use_case(model=_FakeModel(classify_error=ModelUnavailable("down")))
    with pytest.raises(ModelUnavailable):
        await use_case.execute(
            TriageMuseumQuestionInput(question_id="q1", caller=_STAFF)
        )


async def test_get_latest_triage_returns_none_when_never_run() -> None:
    result = await GetLatestTriage(_FakeRepo()).execute(
        GetLatestTriageInput(question_id="q1")
    )
    assert result is None


async def test_get_latest_triage_returns_most_recent() -> None:
    repo = _FakeRepo()
    older = MessageTriage(
        id=TriageId("t1"),
        question_id="q1",
        verdict=TriageVerdict.IN_SCOPE,
        is_visit_related=True,
        mentioned_objects=[],
        object_matches=[],
        suggested_reply=None,
        llm_model="llama3.1:8b",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    newer = MessageTriage(
        id=TriageId("t2"),
        question_id="q1",
        verdict=TriageVerdict.OUT_OF_SCOPE,
        is_visit_related=False,
        mentioned_objects=[],
        object_matches=[],
        suggested_reply="reply",
        llm_model="llama3.1:8b",
        created_at=datetime(2026, 1, 2, tzinfo=UTC),
    )
    await repo.add(older)
    await repo.add(newer)
    latest = await GetLatestTriage(repo).execute(
        GetLatestTriageInput(question_id="q1")
    )
    assert latest == newer
