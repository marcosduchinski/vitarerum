"""Use of Collections access policies (HTTP-free).

Proposal/project ownership rules: staff see everything; a researcher may only
access proposals/projects they requested. Presentation maps AccessDenied to
the contract's 403 ACCESS_DENIED body.
"""

from app.identity.public import Actor
from app.shared.authorization import is_staff
from app.shared.exceptions import AccessDenied
from app.use_of_collections.domain.models import CollectionUseProject, Proposal


def assert_proposal_access(caller: Actor, proposal: Proposal) -> None:
    if is_staff(caller) or proposal.requested_by == caller.id:
        return
    raise AccessDenied("You do not have access to this proposal")


def assert_project_access(
    caller: Actor,
    project: CollectionUseProject,
    project_proposal: Proposal | None,
) -> None:
    """Staff see everything; a researcher may access a project they requested.

    Ownership is read from ``project.requested_by`` directly, not only from
    the linked proposal: a follow-up project (see ``CreateFollowUpProject``)
    has no proposal of its own (``proposal_id is None``, and no ``Proposal``
    ever points back to it via ``collection_use_project_id``), so gating
    solely on ``project_proposal`` would lock out its own requester even
    though ``requested_by`` was copied from the origin project on purpose.
    """
    if is_staff(caller):
        return
    if project.requested_by == caller.id:
        return
    if project_proposal is not None and project_proposal.requested_by == caller.id:
        return
    raise AccessDenied("You do not have access to this project")
