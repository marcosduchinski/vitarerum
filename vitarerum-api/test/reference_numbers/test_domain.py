from datetime import date

import pytest

from app.reference_numbers.domain.models import (
    InvalidReferencePolicyTransition,
    LegacyReferenceFormat,
    ReferenceKind,
    ReferenceMask,
    ReferencePolicy,
    ReferencePolicyStatus,
    SequenceOverflow,
    SequenceScope,
)
from app.shared.kernel import ReferenceNumber


def test_mask_renders_and_derives_year_scope() -> None:
    mask = ReferenceMask("MUHNAC/COL/YYYY/XXXX")

    assert mask.sequence_scope is SequenceScope.YEAR
    assert mask.tokens == ("YYYY", "XXXX")
    assert mask.render(on_date=date(2026, 7, 23), sequence=42) == (
        "MUHNAC/COL/2026/0042"
    )
    assert mask.scope_key(date(2026, 7, 23)) == "2026"


def test_mask_rejects_sequence_that_is_not_final_token() -> None:
    with pytest.raises(ValueError, match="final token"):
        ReferenceMask("MUHNAC/XXXX/YYYY")


def test_mask_sequence_width_is_hard_ceiling() -> None:
    mask = ReferenceMask("VRP-YYYYMMDD-XXXX")

    with pytest.raises(SequenceOverflow):
        mask.render(on_date=date(2026, 7, 23), sequence=10000)


def test_numeric_mask_does_not_validate_legacy_hex_without_legacy_format() -> None:
    mask = ReferenceMask("CUP-XXXXXXXX")
    legacy = LegacyReferenceFormat(
        kind=ReferenceKind.COLLECTION_USE_PROJECT,
        name="legacy-cup-alnum",
        pattern=r"^CUP-[A-Z0-9]{8}$",
    )

    assert mask.to_regex().fullmatch("CUP-00000042") is not None
    assert mask.to_regex().fullmatch("CUP-AB12CD34") is None
    assert legacy.matches("CUP-AB12CD34")


def test_reference_number_wrapper_allows_policy_valid_long_values() -> None:
    reference = ReferenceNumber(" MUHNAC/COL/2026/0001 ")

    assert reference.value == "MUHNAC/COL/2026/0001"


def test_literal_text_containing_a_date_token_substring_is_not_misparsed() -> None:
    """A literal prefix like "COMM" must not be misread as containing an "MM"
    month token just because the letters happen to appear consecutively."""
    mask = ReferenceMask("COMM-XXXX")

    assert mask.tokens == ("XXXX",)
    assert mask.sequence_scope is SequenceScope.GLOBAL
    assert mask.render(on_date=date(2026, 7, 23), sequence=1) == "COMM-0001"
    assert mask.to_regex().fullmatch("COMM-0001") is not None


def test_concatenated_date_tokens_still_parse_correctly() -> None:
    """Unlike a coincidental substring, a run that fully decomposes into
    known date tokens (as in VRP-YYYYMMDD-XXXX) must still be recognized."""
    mask = ReferenceMask("VRP-YYYYMMDD-XXXX")

    assert mask.tokens == ("YYYY", "MM", "DD", "XXXX")
    assert mask.sequence_scope is SequenceScope.DAY


def _draft_policy(mask: str = "MUHNAC/COL/YYYY/XXXX") -> ReferencePolicy:
    return ReferencePolicy.create_draft(
        kind=ReferenceKind.COLLECTION_USE_PROJECT,
        mask=ReferenceMask(mask),
        created_by="perm-admin",
    )


def test_inactive_policy_can_be_reactivated_but_active_cannot_be_activated_again() -> (
    None
):
    policy = _draft_policy()
    active = policy.activate(actor_id="perm-admin")
    inactive = active.deactivate(actor_id="perm-admin")

    # INACTIVE -> ACTIVE is a legitimate re-activation...
    reactivated = inactive.activate(actor_id="perm-admin")
    assert reactivated.status is ReferencePolicyStatus.ACTIVE

    # ...but activating an already-ACTIVE policy is not.
    with pytest.raises(InvalidReferencePolicyTransition):
        reactivated.activate(actor_id="perm-admin")


def test_cannot_activate_a_retired_policy() -> None:
    from dataclasses import replace

    policy = _draft_policy()
    retired = replace(policy, status=ReferencePolicyStatus.RETIRED)

    with pytest.raises(InvalidReferencePolicyTransition):
        retired.activate(actor_id="perm-admin")


def test_cannot_deactivate_a_draft_policy() -> None:
    policy = _draft_policy()

    with pytest.raises(InvalidReferencePolicyTransition):
        policy.deactivate(actor_id="perm-admin")
