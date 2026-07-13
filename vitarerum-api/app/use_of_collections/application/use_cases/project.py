"""Project-phase use cases and the Proposal↔Project bridges.

``CollectionUseProject`` lifecycle (start, complete, cancel) plus the two use
cases that straddle both aggregates in one transaction: ``ApproveProposal``
(spawns the project) and ``CancelProposal`` (cancels the proposal and its linked
project). Concentrating the bridges here keeps the seam in a single place.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from app.identity.public import Actor, GroupName
from app.shared.authorization import require_group
from app.use_of_collections.application.ports import (
    CollectionUseProjectRepository,
    ExternalRequesterProvisioner,
    ObjectAccessLogRepository,
    ObjectOccurrenceLogRepository,
    ProposalRepository,
)
from app.use_of_collections.application.use_cases._shared import (
    _new_access_log_reference_number,
    _new_id,
    _new_reference_number,
    _now,
)
from app.use_of_collections.domain.enums import UseStatus, UseType
from app.use_of_collections.domain.models import (
    CollectionUseObject,
    CollectionUseObjectId,
    CollectionUseProject,
    CollectionUseProjectId,
    ObjectAccessLog,
    ObjectAccessLogId,
    ObjectLogEntry,
    ObjectLogEntryId,
    PermissionId,
    ProjectObjectInUse,
    Proposal,
    ProposalId,
    ReferenceNumber,
)

# ── Approve Proposal ──────────────────────────────────────────────────────────


@dataclass(slots=True)
class ApproveProposalInput:
    proposal_id: ProposalId
    caller: Actor
    title: str
    purpose: str
    begin_date: date
    end_date: date
    note: str | None = None


@dataclass(slots=True)
class RequesterAccessNotification:
    """Pending operational side effect, not a domain event: a newly
    provisioned external requester needs their login credentials e-mailed.
    Carried on the output so the route can dispatch it *after* commit (see
    ``ApproveProposal``)."""

    email: str
    name: str
    temporary_password: str = field(repr=False)


@dataclass(slots=True)
class ApproveProposalOutput:
    proposal: Proposal
    project: CollectionUseProject
    requester_access_notification: RequesterAccessNotification | None = None


class ApproveProposal:
    def __init__(
        self,
        proposal_repository: ProposalRepository,
        project_repository: CollectionUseProjectRepository,
        requester_provisioner: ExternalRequesterProvisioner,
    ) -> None:
        self._proposal_repo = proposal_repository
        self._project_repo = project_repository
        self._requester_provisioner = requester_provisioner

    async def execute(self, data: ApproveProposalInput) -> ApproveProposalOutput:
        require_group(data.caller, GroupName.CURATORIAL)
        if data.end_date < data.begin_date:
            raise ValueError("endDate must be after beginDate")
        proposal = await self._proposal_repo.get_by_id(data.proposal_id)
        if proposal is None:
            raise LookupError(f"No proposal found with id {data.proposal_id}")
        # Fail fast on eligibility before touching Identity: a proposal that
        # isn't PENDING will be rejected by approve() below regardless, so a
        # public proposal must never provision a requester for a decision
        # that was never going to succeed.
        proposal.ensure_approvable()
        requester_access_notification: RequesterAccessNotification | None = None
        if proposal.requested_by is None:
            # Public proposal: Identity provisioning is deferred until this
            # moment, so a rejected/cancelled proposal never creates a user or
            # permission for a contact that never becomes a real requester.
            if proposal.requester_contact is None:
                raise ValueError("proposal requester must be resolved before approval")
            provisioned = await self._requester_provisioner.provision(
                email=proposal.requester_contact.email.value,
                name=proposal.requester_contact.name,
            )
            proposal.resolve_requester(provisioned.actor.id)
            if provisioned.temporary_password is not None:
                requester_access_notification = RequesterAccessNotification(
                    email=proposal.requester_contact.email.value,
                    name=proposal.requester_contact.name,
                    temporary_password=provisioned.temporary_password,
                )
        if proposal.requested_by is None:
            raise ValueError("proposal requester must be resolved before approval")
        requester_id = proposal.requested_by

        now = _now()
        project_id = proposal.collection_use_project_id or CollectionUseProjectId(
            _new_id()
        )
        project = CollectionUseProject(
            id=project_id,
            reference_number=ReferenceNumber(_new_reference_number()),
            title=data.title,
            purpose=data.purpose,
            # A project always has an intended use; a stub proposal may not yet,
            # in which case it defaults to the OTHER (unclassified) category.
            intended_use=proposal.intended_use or UseType.OTHER,
            status=UseStatus.CREATED,
            begin_date=data.begin_date,
            end_date=data.end_date,
            requested_by=requester_id,
            proposal_id=proposal.id,
            # Copy the proposal's requested objects into the project as it is
            # created: the project owns its own object snapshots from here on, so
            # the Project Phase never has to read back into the proposal.
            objects=[
                CollectionUseObject(
                    id=CollectionUseObjectId(_new_id()),
                    inventory_number=ro.inventory_number,
                    category=ro.category,
                    description=ro.description,
                    requested_at=ro.requested_at,
                    requested_by=ro.requested_by or requester_id,
                    display_title=ro.display_title,
                    object_name=ro.object_name,
                    brief_description_snapshot=ro.brief_description_snapshot,
                )
                for ro in proposal.requested_objects
            ],
        )
        project.record_requested(
            occurred_at=now, triggered_by=data.caller.id, note=data.note
        )

        proposal.collection_use_project_id = project_id
        proposal.approve(occurred_at=now, triggered_by=data.caller.id, note=data.note)
        await self._project_repo.add(project)
        await self._proposal_repo.save(proposal)
        return ApproveProposalOutput(
            proposal=proposal,
            project=project,
            requester_access_notification=requester_access_notification,
        )


# ── Cancel Proposal ───────────────────────────────────────────────────────────


@dataclass(slots=True)
class CancelProposalInput:
    proposal_id: ProposalId
    caller: Actor
    reason: str


@dataclass(slots=True)
class CancelProposalOutput:
    proposal: Proposal
    project: CollectionUseProject | None = None


class CancelProposal:
    def __init__(
        self,
        proposal_repository: ProposalRepository,
        project_repository: CollectionUseProjectRepository,
    ) -> None:
        self._proposal_repo = proposal_repository
        self._project_repo = project_repository

    async def execute(self, data: CancelProposalInput) -> CancelProposalOutput:
        proposal = await self._proposal_repo.get_by_id(data.proposal_id)
        if proposal is None:
            raise LookupError(f"No proposal found with id {data.proposal_id}")
        if proposal.requested_by != data.caller.id:
            raise PermissionError("Only the requester can cancel this proposal")

        now = _now()
        proposal.cancel(
            occurred_at=now, triggered_by=data.caller.id, reason=data.reason
        )

        project = (
            await self._project_repo.get_by_id(proposal.collection_use_project_id)
            if proposal.collection_use_project_id is not None
            else None
        )
        if project is not None:
            project.record_cancelled_from_proposal(
                occurred_at=now,
                triggered_by=data.caller.id,
                reason=data.reason,
            )
            await self._project_repo.save(project)

        await self._proposal_repo.save(proposal)
        return CancelProposalOutput(proposal=proposal, project=project)


# ── Project commands ──────────────────────────────────────────────────────────


@dataclass(slots=True)
class EditProjectDetailsInput:
    project_id: CollectionUseProjectId
    caller: Actor
    title: str | None = None
    update_title: bool = False
    purpose: str | None = None
    update_purpose: bool = False
    begin_date: date | None = None
    update_begin_date: bool = False
    end_date: date | None = None
    update_end_date: bool = False


class EditProjectDetails:
    def __init__(self, project_repository: CollectionUseProjectRepository) -> None:
        self._repo = project_repository

    async def execute(self, data: EditProjectDetailsInput) -> CollectionUseProject:
        project = await self._repo.get_by_id(data.project_id)
        if project is None:
            raise LookupError(f"No project found with id {data.project_id}")
        project.edit(
            title=data.title,
            update_title=data.update_title,
            purpose=data.purpose,
            update_purpose=data.update_purpose,
            begin_date=data.begin_date,
            update_begin_date=data.update_begin_date,
            end_date=data.end_date,
            update_end_date=data.update_end_date,
        )
        await self._repo.save(project)
        return project


@dataclass(slots=True)
class ProjectObjectSnapshotInput:
    inventory_number: str
    display_title: str
    object_name: str
    brief_description_snapshot: str | None = None
    category: str = ""
    description: str = ""


@dataclass(slots=True)
class AddProjectObjectsInput:
    project_id: CollectionUseProjectId
    caller: Actor
    objects: list[ProjectObjectSnapshotInput]


class AddProjectObjects:
    def __init__(self, project_repository: CollectionUseProjectRepository) -> None:
        self._repo = project_repository

    async def execute(self, data: AddProjectObjectsInput) -> CollectionUseProject:
        project = await self._repo.get_by_id(data.project_id)
        if project is None:
            raise LookupError(f"No project found with id {data.project_id}")
        now = _now()
        objects = [
            CollectionUseObject(
                id=CollectionUseObjectId(_new_id()),
                inventory_number=item.inventory_number,
                display_title=item.display_title,
                object_name=item.object_name,
                brief_description_snapshot=item.brief_description_snapshot,
                category=item.category,
                description=item.description,
                requested_at=now,
                requested_by=data.caller.id,
            )
            for item in data.objects
        ]
        for item in objects:
            if not item.display_title or not item.display_title.strip():
                raise ValueError("displayTitle is required.")
            if not item.object_name or not item.object_name.strip():
                raise ValueError("objectName is required.")
        project.add_objects(objects)
        await self._repo.save(project)
        return project


@dataclass(slots=True)
class RemoveProjectObjectInput:
    project_id: CollectionUseProjectId
    collection_use_object_id: CollectionUseObjectId
    caller: Actor


class RemoveProjectObject:
    def __init__(
        self,
        project_repository: CollectionUseProjectRepository,
        access_log_repository: ObjectAccessLogRepository,
        occurrence_log_repository: ObjectOccurrenceLogRepository,
    ) -> None:
        self._project_repo = project_repository
        self._access_log_repo = access_log_repository
        self._occurrence_log_repo = occurrence_log_repository

    async def execute(self, data: RemoveProjectObjectInput) -> CollectionUseProject:
        project = await self._project_repo.get_by_id(data.project_id)
        if project is None:
            raise LookupError(f"No project found with id {data.project_id}")
        if await self._access_log_repo.has_entries_for_object(
            data.project_id, data.collection_use_object_id
        ) or await self._occurrence_log_repo.has_entries_for_object(
            data.project_id, data.collection_use_object_id
        ):
            raise ProjectObjectInUse(
                f"Project object {data.collection_use_object_id} has log or "
                "occurrence entries"
            )
        project.remove_object(data.collection_use_object_id)
        await self._project_repo.save(project)
        return project


@dataclass(slots=True)
class StartProjectInput:
    project_id: CollectionUseProjectId
    caller: Actor
    note: str | None = None


class StartProject:
    def __init__(
        self,
        project_repository: CollectionUseProjectRepository,
        access_log_repository: ObjectAccessLogRepository,
    ) -> None:
        self._repo = project_repository
        self._access_log_repo = access_log_repository

    async def execute(self, data: StartProjectInput) -> CollectionUseProject:
        project = await self._repo.get_by_id(data.project_id)
        if project is None:
            raise LookupError(f"No project found with id {data.project_id}")
        now = _now()
        project.record_started(
            occurred_at=now, triggered_by=data.caller.id, note=data.note
        )
        await self._repo.save(project)
        # Materialise the access log as work begins: the project's own objects are
        # the ones that will be handled, so each becomes a registered
        # ObjectLogEntry (quantity defaults to 1), linked back to its
        # CollectionUseObject for end-to-end traceability.
        await self._seed_access_log_from_objects(project, data.caller.id, now)
        return project

    async def _seed_access_log_from_objects(
        self,
        project: CollectionUseProject,
        caller_id: PermissionId,
        now: datetime,
    ) -> None:
        if not project.objects:
            return
        # Only seed when the log does not exist yet; if entries were already
        # added (e.g. by staff before start) we leave it untouched.
        if await self._access_log_repo.get_by_project_id(project.id) is not None:
            return
        access_log = ObjectAccessLog(
            id=ObjectAccessLogId(_new_id()),
            reference_number=ReferenceNumber(_new_access_log_reference_number()),
            collection_use_project_id=project.id,
        )
        await self._access_log_repo.add(access_log)
        for obj in project.objects:
            entry = ObjectLogEntry(
                id=ObjectLogEntryId(_new_id()),
                object_access_log_id=access_log.id,
                collection_use_object_id=obj.id,
                number_of_objects=1,
                added_at=now,
                added_by=caller_id,
            )
            access_log.add_object_log_entry(entry)
            await self._access_log_repo.save_entry(entry)


@dataclass(slots=True)
class CompleteProjectInput:
    project_id: CollectionUseProjectId
    caller: Actor
    note: str | None = None


class CompleteProject:
    def __init__(self, project_repository: CollectionUseProjectRepository) -> None:
        self._repo = project_repository

    async def execute(self, data: CompleteProjectInput) -> CollectionUseProject:
        project = await self._repo.get_by_id(data.project_id)
        if project is None:
            raise LookupError(f"No project found with id {data.project_id}")
        project.record_completed(
            occurred_at=_now(), triggered_by=data.caller.id, note=data.note
        )
        await self._repo.save(project)
        return project


@dataclass(slots=True)
class CancelProjectInput:
    project_id: CollectionUseProjectId
    caller: Actor
    reason: str


class CancelProject:
    def __init__(self, project_repository: CollectionUseProjectRepository) -> None:
        self._repo = project_repository

    async def execute(self, data: CancelProjectInput) -> CollectionUseProject:
        project = await self._repo.get_by_id(data.project_id)
        if project is None:
            raise LookupError(f"No project found with id {data.project_id}")
        project.record_cancelled(
            occurred_at=_now(), triggered_by=data.caller.id, reason=data.reason
        )
        await self._repo.save(project)
        return project
