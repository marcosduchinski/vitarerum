"""Use of Collections access policies (HTTP-free).

Proposal/project ownership rules: staff see everything; a researcher may only
access proposals/projects they requested. Presentation maps AccessDenied to
the contract's 403 ACCESS_DENIED body.
"""

from app.identity.public import Actor
from app.shared.authorization import is_staff
from app.shared.exceptions import AccessDenied
from app.use_of_collections.domain.models import Proposal


def assert_proposal_access(caller: Actor, proposal: Proposal) -> None:
    if is_staff(caller) or proposal.requested_by == caller.id:
        return
    raise AccessDenied("You do not have access to this proposal")


def assert_project_access(
    caller: Actor,
    project_proposal: Proposal | None,
) -> None:
    if is_staff(caller):
        return
    if project_proposal is not None and project_proposal.requested_by == caller.id:
        return
    raise AccessDenied("You do not have access to this project")
