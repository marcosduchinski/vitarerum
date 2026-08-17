"""Deterministic comparison of verified evidence before and after a tool ran.

The delta is computed from the evidence rows the system itself produced, never
from what the model says it found. That is what makes it reproducible: running
the same tool over the same records yields the same delta and the same hashes,
so a stored trajectory can be re-checked long after the fact.
"""

from __future__ import annotations

from collections.abc import Iterable

from app.scientific_return.domain.investigation_contracts import EvidenceDelta
from app.scientific_return.domain.models import CandidateEvidence

_EvidenceKey = tuple[str, str, str, str, str]


def evidence_identity(evidence: CandidateEvidence) -> _EvidenceKey:
    """Identity of one piece of evidence, ignoring its row id and timestamp.

    Two evidence rows produced by separate runs over the same record are the
    same finding and must not read as a change.
    """
    return (
        str(evidence.type),
        str(evidence.strength),
        evidence.value,
        evidence.source_field,
        evidence.object_id or "",
    )


def evidence_hash(evidences: Iterable[CandidateEvidence]) -> str:
    """Order-independent hash of a set of verified evidence."""
    import hashlib

    keys = sorted("|".join(evidence_identity(item)) for item in evidences)
    return hashlib.sha256("\n".join(keys).encode("utf-8")).hexdigest()


def calculate_evidence_delta(
    before: Iterable[CandidateEvidence],
    after: Iterable[CandidateEvidence],
) -> EvidenceDelta:
    """Compare two sets of verified evidence.

    ``removed`` should stay empty in normal operation: the cycle only appends.
    It is reported rather than asserted so that a rule change which silently
    drops evidence shows up in the trajectory instead of passing unnoticed.
    """
    before_map = {evidence_identity(item): item for item in before}
    after_map = {evidence_identity(item): item for item in after}

    added = tuple(
        dict.fromkeys(
            evidence.type
            for key, evidence in after_map.items()
            if key not in before_map
        )
    )
    preserved = tuple(
        dict.fromkeys(
            evidence.type for key, evidence in after_map.items() if key in before_map
        )
    )
    removed = tuple(
        dict.fromkeys(
            evidence.type
            for key, evidence in before_map.items()
            if key not in after_map
        )
    )
    return EvidenceDelta(added=added, preserved=preserved, removed=removed)
