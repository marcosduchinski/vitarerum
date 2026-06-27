"""ProposalChat access policy (HTTP-free).

Triage is a staff action. We raise ``AccessDenied`` (not ``InsufficientGroup``)
so presentation maps it to the contract's ``403 ACCESS_DENIED`` body with the
"Triage is restricted to staff members" message, exactly as 07Proposalchat-api.md
specifies.
"""

from app.identity.public import Actor
from app.shared.authorization import is_staff
from app.shared.exceptions import AccessDenied


def assert_triage_access(caller: Actor) -> None:
    if is_staff(caller):
        return
    raise AccessDenied("Triage is restricted to staff members")
