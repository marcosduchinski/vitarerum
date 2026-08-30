from app.scientific_return.application.full_agentic_strategy import (
    bare_inventory_query,
    bibliographic_surname_hypotheses,
    deterministic_floor,
    discovery_floor,
    inventory_floor,
    search_is_supported,
    source_result_limit,
    suggested_inventory_variants,
)
from app.scientific_return.application.ports import BibliographicSourceCapabilities
from app.scientific_return.domain.enums import SearchIntent, SearchStrategy
from app.scientific_return.domain.full_agentic_models import AgenticSearchSpec
from app.scientific_return.domain.models import (
    ConsultedObjectSnapshot,
    ProjectSnapshotPayload,
)


def _snapshot(researcher: str = "Pedro Gomes") -> ProjectSnapshotPayload:
    return ProjectSnapshotPayload(
        project_id="project-1",
        project_reference="P-1",
        researcher=researcher,
        consulted_objects=(
            ConsultedObjectSnapshot(
                id="object-1",
                inventory_number="MUHNAC/MB04-001066",
                object_name="Cynoscion regalis",
            ),
        ),
    )


def test_surname_hypotheses_preserve_particles() -> None:
    assert bibliographic_surname_hypotheses("Maria da Silva") == (
        "da Silva",
        "Silva",
    )


def test_surname_hypotheses_keep_a_short_ambiguous_compound_option() -> None:
    assert bibliographic_surname_hypotheses("Ana Silva Costa") == (
        "Silva Costa",
        "Costa",
    )


def test_surname_hypotheses_do_not_treat_an_initial_as_a_surname() -> None:
    assert bibliographic_surname_hypotheses("Mariana P. Marques") == ("Marques",)


def test_floor_routes_author_separately_to_structured_source() -> None:
    source = BibliographicSourceCapabilities(
        name="OPENALEX",
        searches_metadata=True,
        searches_indexed_full_text=True,
        returns_abstract=True,
        returns_inspectable_full_text=False,
        supports_structured_author=True,
    )

    search = discovery_floor(_snapshot(), (source,), 1)[0]

    assert search.query == '"Cynoscion regalis"'
    assert search.author == "Gomes"
    assert search.strategy is SearchStrategy.AUTHOR_OBJECT


def test_bare_inventory_variant_is_suggested_before_aliases() -> None:
    suggestions = suggested_inventory_variants(_snapshot())

    assert suggestions[0]["text"] == "MB04-001066"
    assert all(item["kind"] != "SEPARATOR" for item in suggestions)


def test_inventory_evidence_is_routed_only_to_an_inspectable_source() -> None:
    search = AgenticSearchSpec(
        source="OPENALEX",
        query='"MB04-001066"',
        intent=SearchIntent.INVENTORY_EVIDENCE,
        strategy=SearchStrategy.INVENTORY_QUERY,
    )
    metadata_only = BibliographicSourceCapabilities(
        name="OPENALEX",
        searches_metadata=True,
        searches_indexed_full_text=True,
        returns_abstract=True,
        returns_inspectable_full_text=False,
        supports_structured_author=True,
    )
    full_text = BibliographicSourceCapabilities(
        name="EUROPE_PMC",
        searches_metadata=True,
        searches_indexed_full_text=True,
        returns_abstract=True,
        returns_inspectable_full_text=True,
        supports_structured_author=False,
    )

    assert search_is_supported(search, metadata_only) is False
    assert search_is_supported(search, full_text) is True


def test_discovery_is_routed_to_any_metadata_source() -> None:
    search = AgenticSearchSpec(
        source="CROSSREF",
        query='"Cynoscion regalis"',
        intent=SearchIntent.DISCOVERY,
        strategy=SearchStrategy.OBJECT_QUERY,
    )
    crossref = BibliographicSourceCapabilities(
        name="CROSSREF",
        searches_metadata=True,
        searches_indexed_full_text=False,
        returns_abstract=True,
        returns_inspectable_full_text=False,
        supports_structured_author=False,
    )

    assert search_is_supported(search, crossref) is True


_FULL_TEXT = BibliographicSourceCapabilities(
    name="EUROPE_PMC",
    searches_metadata=True,
    searches_indexed_full_text=True,
    returns_abstract=True,
    returns_inspectable_full_text=True,
    supports_structured_author=False,
)
_METADATA_ONLY = BibliographicSourceCapabilities(
    name="CROSSREF",
    searches_metadata=True,
    searches_indexed_full_text=False,
    returns_abstract=True,
    returns_inspectable_full_text=False,
    supports_structured_author=False,
)


def test_the_bare_code_is_preferred_over_the_recorded_string() -> None:
    assert bare_inventory_query("MUHNAC/MB04-001066") == "MB04-001066"


def test_a_number_without_an_institution_prefix_keeps_its_exact_form() -> None:
    assert bare_inventory_query("MB04-001066") == "MB04-001066"


def test_the_inventory_floor_does_not_depend_on_the_planner() -> None:
    searches = inventory_floor(_snapshot(), (_FULL_TEXT,), 4)

    assert [search.query for search in searches] == ['"MB04-001066"']
    assert searches[0].intent is SearchIntent.INVENTORY_EVIDENCE
    assert searches[0].strategy is SearchStrategy.INVENTORY_QUERY
    assert searches[0].source == "EUROPE_PMC"
    assert searches[0].author is None


def test_the_inventory_floor_refuses_a_source_that_cannot_prove_the_claim() -> None:
    """On a metadata-only index the absence of the code would prove nothing."""
    assert inventory_floor(_snapshot(), (_METADATA_ONLY,), 4) == ()


def test_the_floor_covers_both_strategies_within_one_reservation() -> None:
    searches = deterministic_floor(_snapshot(), (_FULL_TEXT,), 4)

    assert [search.strategy for search in searches] == [
        SearchStrategy.AUTHOR_OBJECT,
        SearchStrategy.INVENTORY_QUERY,
    ]


def test_the_floor_never_exceeds_its_reservation() -> None:
    snapshot = _snapshot()
    searches = deterministic_floor(snapshot, (_FULL_TEXT,), 1)

    assert len(searches) == 1
    # The author and object guarantee survives the smallest reservation.
    assert searches[0].strategy is SearchStrategy.AUTHOR_OBJECT


def test_a_metadata_only_source_gets_a_smaller_share_of_the_results() -> None:
    """Crossref answers broadly and ranks weakly, and every record it returns
    still costs one reader call."""
    assert source_result_limit(_METADATA_ONLY, 40) == 10


def test_a_full_text_source_keeps_the_general_ceiling() -> None:
    assert source_result_limit(_FULL_TEXT, 40) == 20


def test_the_measured_worst_useful_rank_still_fits() -> None:
    """Crossref returned its five fixture matches at ranks 1, 2, 3, 4 and 7."""
    assert source_result_limit(_METADATA_ONLY, 40) > 7


def test_a_small_budget_binds_before_the_capability_rule() -> None:
    assert source_result_limit(_METADATA_ONLY, 3) == 3
    assert source_result_limit(_FULL_TEXT, 3) == 3


def test_an_undeclared_source_keeps_the_general_ceiling() -> None:
    assert source_result_limit(None, 40) == 20


_OPENALEX = BibliographicSourceCapabilities(
    name="OPENALEX",
    searches_metadata=True,
    searches_indexed_full_text=True,
    returns_abstract=True,
    returns_inspectable_full_text=False,
    supports_structured_author=True,
)
_CROSSREF = BibliographicSourceCapabilities(
    name="CROSSREF",
    searches_metadata=True,
    searches_indexed_full_text=False,
    returns_abstract=True,
    returns_inspectable_full_text=False,
    supports_structured_author=False,
)
_EUROPE_PMC = BibliographicSourceCapabilities(
    name="EUROPE_PMC",
    searches_metadata=True,
    searches_indexed_full_text=True,
    returns_abstract=True,
    returns_inspectable_full_text=True,
    supports_structured_author=False,
)
_ALL_THREE = (_OPENALEX, _CROSSREF, _EUROPE_PMC)


def test_discovery_asks_every_source_that_can_answer() -> None:
    """No single index reaches every expected publication; together they do.

    Measured over the eight cases with a recorded expectation: OpenAlex five,
    Crossref six, Europe PMC five, union eight. Asking only the best-ranked
    source made the guarantee depend on one index knowing the taxon.
    """
    searches = discovery_floor(_snapshot(), _ALL_THREE, 1)

    assert [search.source for search in searches] == [
        "OPENALEX",
        "EUROPE_PMC",
        "CROSSREF",
    ]
    # Only the structured-author index is told the surname separately.
    assert searches[0].query == '"Cynoscion regalis"'
    assert all(search.author == "Gomes" for search in searches)
    assert all('"Gomes"' in search.query for search in searches[1:])


def test_extra_discovery_sources_never_push_out_the_inventory_leg() -> None:
    """Each object keeps its best discovery source and its inventory code.

    Grouping the three discovery searches together would spend the reservation
    on them and leave every object after the first without an inventory query —
    trading one guarantee of the floor for the other.
    """
    snapshot = ProjectSnapshotPayload(
        project_id="project-1",
        project_reference="P-1",
        researcher="Pedro Gomes",
        consulted_objects=(
            ConsultedObjectSnapshot("object-1", "MUHNAC/MB04-001066", "Taxon one"),
            ConsultedObjectSnapshot("object-2", "MUHNAC/MB04-001067", "Taxon two"),
        ),
    )

    searches = deterministic_floor(snapshot, _ALL_THREE, 6)

    for object_id in ("object-1", "object-2"):
        strategies = [
            search.strategy for search in searches if search.object_id == object_id
        ]
        assert SearchStrategy.AUTHOR_OBJECT in strategies
        assert SearchStrategy.INVENTORY_QUERY in strategies
    assert searches[0].strategy is SearchStrategy.AUTHOR_OBJECT
