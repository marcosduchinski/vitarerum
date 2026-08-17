from __future__ import annotations

import pytest

from app.scientific_return.domain.enums import InventoryVariantKind
from app.scientific_return.domain.inventory_variants import (
    comparison_key,
    generate_inventory_query_variants,
)


def _texts(inventory: str, **kwargs: object) -> list[str]:
    return [
        variant.text
        for variant in generate_inventory_query_variants(inventory, **kwargs)  # type: ignore[arg-type]
    ]


def test_the_recorded_form_is_always_tried_first() -> None:
    variants = generate_inventory_query_variants("MUHNAC/MB03-001522")

    assert variants[0].text == "MUHNAC/MB03-001522"
    assert variants[0].kind is InventoryVariantKind.EXACT


def test_bare_collection_code_is_generated() -> None:
    """Five of the MUHNAC papers cite the code without any institutional prefix."""
    variants = generate_inventory_query_variants("MUHNAC/MB06-005747")

    assert variants[1].text == "MB06-005747"
    assert variants[1].kind is InventoryVariantKind.WITHOUT_INSTITUTION


def test_zero_padding_is_varied_in_both_directions() -> None:
    padded = _texts("MUHNAC/MB03-001522")
    unpadded = _texts("MUHNAC/MB03-1707")

    assert "MB03-1522" in padded
    assert "MB03-001707" in unpadded


def test_known_institutional_acronyms_are_generated() -> None:
    variants = _texts("MUHNAC/MB04-001066")

    assert "MUNHAC/MB04-001066" in variants
    assert "MNHNC/MB04-001066" in variants
    assert "MNHNUL/MB04-001066" in variants


def test_colon_composed_form_is_generated() -> None:
    """``MNHNC:MB11:001283`` is how the subterranean-biology paper cites it."""
    assert "MNHNC:MB11:001283" in _texts("MUHNAC/MB11-001283")


def test_separator_alternatives_are_generated() -> None:
    variants = _texts("MUHNAC/MB28-005003")

    assert "MB28 005003" in variants
    assert "MB28005003" in variants
    assert "MB28:005003" in variants


def test_the_recorded_acronym_is_not_repeated_as_an_alias() -> None:
    variants = _texts("MUNHAC/MB03-001552")

    assert variants.count("MUNHAC/MB03-001552") == 1
    assert "MUHNAC/MB03-001552" in variants


def test_variants_are_deduplicated_and_stable() -> None:
    variants = _texts("MUHNAC/MB06-005861")

    assert len(variants) == len(set(variants))
    assert variants == _texts("MUHNAC/MB06-005861")


def test_separator_variants_stay_distinct_from_each_other() -> None:
    """Compacting for comparison would collapse genuinely different queries."""
    variants = _texts("MUHNAC/MB06-005747")

    assert {"MB06-005747", "MB06 005747", "MB06005747"} <= set(variants)


def test_queries_already_issued_are_removed() -> None:
    variants = _texts(
        "MUHNAC/MB03-001522",
        already_tried=['"MUHNAC/MB03-001522"', "MB03-001522"],
    )

    assert "MUHNAC/MB03-001522" not in variants
    assert "MB03-001522" not in variants
    assert variants


def test_nothing_is_left_when_every_variant_was_tried() -> None:
    every = _texts("MUHNAC/MB03-001522")

    assert generate_inventory_query_variants(
        "MUHNAC/MB03-001522", already_tried=every
    ) == ()


def test_the_limit_is_applied_after_filtering() -> None:
    variants = generate_inventory_query_variants(
        "MUHNAC/MB06-005747",
        already_tried=['"MUHNAC/MB06-005747"'],
        limit=4,
    )

    assert len(variants) == 4
    assert variants[0].text == "MB06-005747"


@pytest.mark.parametrize(
    "recorded",
    ["MUHNAC / MB03 - 001522", "muhnac/mb03-001522", "  MUHNAC/MB03-001522  "],
)
def test_spacing_and_case_are_tolerated(recorded: str) -> None:
    assert "MB03-001522" in _texts(recorded)


def test_an_unparsable_number_still_tries_the_recorded_form() -> None:
    variants = generate_inventory_query_variants("MNHNCENT0062867")

    assert [variant.text for variant in variants] == ["MNHNCENT0062867"]
    assert variants[0].kind is InventoryVariantKind.EXACT


def test_a_blank_number_produces_nothing() -> None:
    assert generate_inventory_query_variants("   ") == ()


def test_comparison_key_ignores_quoting_but_not_separators() -> None:
    assert comparison_key('"MB06-005747"') == comparison_key("MB06-005747")
    assert comparison_key("MB06-005747") != comparison_key("MB06 005747")
