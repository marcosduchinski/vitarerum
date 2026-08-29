"""Which records are the same publication, whatever their own identifier says.

Indexes register the parts of an article as works in their own right. Pensoft
mints a DOI per figure by extending the article's — ``10.3897/bdj.14.e188597``
becomes ``…e188597.figure4a`` — and Zenodo deposits figures and tables under
unrelated DOIs whose titles name the parent instead: "FIGURE 8. Living animals.
A-D in The most wanted! …".

Deduplication by DOI treats each of those as a separate candidate, which is why
one article once filled a five-candidate review queue with four of its own
figures. That is not a judgement a curator should be asked to make five times,
and it is not merely noise: the ceiling stops the search, so the near-duplicates
displace candidates that would otherwise have been looked for.

The rule is deliberately narrow. It only collapses records that *say* they are
part of another work; anything it cannot resolve keeps its own identity, because
losing a publication silently is worse than presenting one twice.
"""

from __future__ import annotations

import re

# A component DOI extends its parent's with a typed segment.
_COMPONENT_DOI = re.compile(
    r"^(?P<parent>10\.\d{4,9}/\S+?)[./-]"
    r"(?:figure|fig|table|tab|supp|suppl|s)\d+[a-z]?$",
    re.IGNORECASE,
)
# A component title names its parent after "in".
_COMPONENT_TITLE = re.compile(
    r"^\s*(?:figure|fig\.?|table|tab\.?|plate|appendix)\b[^.]*?\.?\s+"
    r"(?:.*?\s)??in\s+(?P<parent>\S.+)$",
    re.IGNORECASE | re.DOTALL,
)
_WHITESPACE = re.compile(r"\s+")


def _normalise(value: str) -> str:
    return _WHITESPACE.sub(" ", value).strip().casefold()


def _clean_doi(doi: str) -> str:
    return _normalise(doi).removeprefix("https://doi.org/").removeprefix("doi:")


def parent_publication(doi: str | None, title: str) -> str | None:
    """The work this record is a part of, or ``None`` if it stands alone."""
    if doi:
        match = _COMPONENT_DOI.match(_clean_doi(doi))
        if match:
            return f"doi:{match.group('parent')}"
    match = _COMPONENT_TITLE.match(title or "")
    if match:
        parent = _normalise(match.group("parent"))
        # A title that trails off mid-sentence still names the same parent for
        # every sibling, which is all this needs to group them.
        return f"title:{parent}" if parent else None
    return None


def publication_identity(doi: str | None, title: str, fallback: str) -> str:
    """The identity under which this record competes for a place in the queue.

    ``fallback`` is the record's own deduplication key, used whenever the record
    is not recognisable as part of something else.
    """
    return parent_publication(doi, title) or fallback


def is_component(doi: str | None, title: str) -> bool:
    return parent_publication(doi, title) is not None
