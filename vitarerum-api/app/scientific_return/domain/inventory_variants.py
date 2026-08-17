"""Deterministic rewriting of an inventory number into search queries.

This is not the inventory normaliser used to *compare* text. That one
(``_compact_inventory`` in the analysis module) strips every separator to make
matching robust, producing strings such as ``MUHNACMB06005747`` that no
bibliographic source indexes. Feeding it to a search API retrieves nothing.

The deterministic pipeline already queries the recorded form verbatim, so the
agentic cycle only adds value when it asks for forms that were *not* tried. The
rules below come from how MUHNAC material is actually cited in the literature:

- bare collection code, with no institutional prefix (``MB06-005747``);
- alternative institutional acronyms, including the ``MUNHAC`` misspelling and
  the ``MNHNC``/``MNHNUL`` forms used by different journals;
- colon-separated composition (``MNHNC:MB11:001283``);
- inconsistent zero padding, which the museum's own records also show
  (``MUHNAC/MB03-1707`` next to ``MUHNAC/MB03-001522``).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from app.scientific_return.domain.enums import InventoryVariantKind

INSTITUTION_ALIASES: tuple[str, ...] = ("MNHNC", "MUNHAC", "MNHNUL", "MUHNAC")
"""Institutional acronyms observed for the same collection, most attested first.

Order matters because the query budget is small: with four queries, a variant
ranked seventh is never asked for. ``MNHNC`` leads because two of the surveyed
articles use it, against one for ``MUNHAC``.
"""

_ALIAS_SEPARATORS: dict[str, str] = {
    # Each alias is first tried in the shape that alias is actually printed in:
    # ``MNHNC:MB11:001283`` but ``MUNHAC/MB03-001552``. Trying an alias in a
    # shape nobody writes wastes a query.
    "MNHNC": ":",
    "MUNHAC": "/",
    "MNHNUL": "/",
    "MUHNAC": "/",
}

CANONICAL_NUMBER_WIDTH = 6
"""Width the museum pads sequential numbers to, e.g. ``001522``."""

_ALTERNATIVE_SEPARATORS: tuple[str, ...] = (" ", "", ":")

_STRUCTURE = re.compile(
    r"^(?:(?P<institution>[A-Za-z]{2,10})\s*[/:.\-]\s*)?"
    r"(?P<collection>[A-Za-z]{2}\s*\d{2})\s*[/:.\-]?\s*"
    r"(?P<number>\d{1,8})$"
)


@dataclass(frozen=True, slots=True)
class InventoryQueryVariant:
    """One search string derived from a recorded inventory number."""

    text: str
    kind: InventoryVariantKind


@dataclass(frozen=True, slots=True)
class _Structure:
    institution: str | None
    collection: str
    number: str


def comparison_key(value: str) -> str:
    """Key used to tell two queries apart.

    Surrounding quotes and repeated whitespace are irrelevant, but separators
    are not: ``MB06-005747`` and ``MB06 005747`` are different queries and both
    are worth trying.
    """
    return " ".join(value.replace('"', " ").split()).upper()


def _collapse(value: str) -> str:
    return " ".join(value.split())


def _parse(inventory_number: str) -> _Structure | None:
    match = _STRUCTURE.match(_collapse(inventory_number))
    if match is None:
        return None
    institution = match.group("institution")
    return _Structure(
        institution=institution.upper() if institution else None,
        collection=match.group("collection").replace(" ", "").upper(),
        number=match.group("number"),
    )


def _compose(alias: str, collection: str, number: str, separator: str) -> str:
    """Build an institutional form. A colon separates all three parts; a slash
    separates the institution and keeps the hyphen inside the code."""
    if separator == ":":
        return f"{alias}:{collection}:{number}"
    return f"{alias}{separator}{collection}-{number}"


def _number_forms(number: str) -> tuple[str, ...]:
    stripped = number.lstrip("0") or "0"
    padded = stripped.rjust(CANONICAL_NUMBER_WIDTH, "0")
    return tuple(dict.fromkeys((number, stripped, padded)))


def generate_inventory_query_variants(
    inventory_number: str,
    *,
    already_tried: Iterable[str] = (),
    limit: int | None = None,
) -> tuple[InventoryQueryVariant, ...]:
    """Rewrite ``inventory_number`` into ordered, deduplicated query strings.

    Variants are ordered by how often each form appears in the literature, so a
    caller that can only afford a few queries spends them on the likeliest
    forms. ``already_tried`` removes queries the watch has already issued, which
    is what keeps the agentic cycle from repeating the deterministic pipeline;
    when nothing new remains the result is empty and the caller must reject the
    action instead of contacting a source.
    """
    recorded = _collapse(inventory_number)
    if not recorded:
        return ()

    structure = _parse(recorded)
    candidates: list[InventoryQueryVariant] = [
        InventoryQueryVariant(recorded, InventoryVariantKind.EXACT)
    ]
    if structure is not None:
        candidates.extend(_structured_variants(structure))

    excluded = {comparison_key(item) for item in already_tried}
    variants: list[InventoryQueryVariant] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = comparison_key(candidate.text)
        if key in seen or key in excluded:
            continue
        seen.add(key)
        variants.append(candidate)
        if limit is not None and len(variants) >= limit:
            break
    return tuple(variants)


def _structured_variants(
    structure: _Structure,
) -> tuple[InventoryQueryVariant, ...]:
    numbers = _number_forms(structure.number)
    primary = numbers[0]
    variants: list[InventoryQueryVariant] = [
        InventoryQueryVariant(
            f"{structure.collection}-{primary}",
            InventoryVariantKind.WITHOUT_INSTITUTION,
        )
    ]
    variants.extend(
        InventoryQueryVariant(
            f"{structure.collection}-{number}",
            InventoryVariantKind.NUMBER_PADDING,
        )
        for number in numbers[1:]
    )
    aliases = tuple(
        alias for alias in INSTITUTION_ALIASES if alias != structure.institution
    )
    # Preferred shapes for every alias come before any alternate shape, so a
    # four-query budget spends itself on forms that are actually printed.
    variants.extend(
        InventoryQueryVariant(
            _compose(alias, structure.collection, primary, _ALIAS_SEPARATORS[alias]),
            InventoryVariantKind.INSTITUTION_ALIAS,
        )
        for alias in aliases
    )
    variants.extend(
        InventoryQueryVariant(
            _compose(
                alias,
                structure.collection,
                primary,
                "/" if _ALIAS_SEPARATORS[alias] == ":" else ":",
            ),
            InventoryVariantKind.INSTITUTION_ALIAS,
        )
        for alias in aliases
    )
    variants.extend(
        InventoryQueryVariant(
            f"{structure.collection}{separator}{primary}",
            InventoryVariantKind.SEPARATOR,
        )
        for separator in _ALTERNATIVE_SEPARATORS
    )
    return tuple(variants)
