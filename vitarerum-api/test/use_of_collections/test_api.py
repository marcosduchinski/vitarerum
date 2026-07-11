import io
import zipfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime

from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.database import get_async_session
from app.identity.infrastructure.models import (
    GroupRecord,
    PermissionRecord,
    UserRecord,
)
from app.identity.public import Actor, GroupName, PermissionId
from app.main import app
from app.shared.dependencies import get_caller_permission
from app.use_of_collections.application.ports import (
    ProjectFilters,
    ProposalFilters,
    ResolvedExternalRequester,
)
from app.use_of_collections.domain.enums import (
    ProposalStatus,
    UseStatus,
    UseType,
)
from app.use_of_collections.domain.models import (
    CollectionUseObject,
    CollectionUseObjectId,
    CollectionUseProject,
    CollectionUseProjectId,
    Conversation,
    ConversationId,
    Document,
    DocumentId,
    DocumentType,
    EmailAddress,
    Message,
    MessageId,
    ObjectAccessLog,
    ObjectAccessLogId,
    ObjectLogEntry,
    ObjectLogEntryId,
    ObjectOccurrenceEntry,
    ObjectOccurrenceLog,
    Proposal,
    ProposalId,
    PublicationLog,
    PublicationLogEntry,
    ReferenceNumber,
    RequesterContact,
)
from app.use_of_collections.presentation.dependencies import (
    get_access_log_repo,
    get_conversation_repo,
    get_external_requester_provisioner,
    get_file_storage,
    get_occurrence_log_repo,
    get_project_repo,
    get_proposal_repo,
    get_publication_log_repo,
    get_requester_access_email_sender,
)


def _docx_bytes() -> bytes:
    """Minimal valid DOCX: a ZIP carrying the OOXML content-types part."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", "<w:document/>")
    return buf.getvalue()


_CALLER = Actor(
    id=PermissionId("permission-1"),
    group=GroupName.EXTERNAL,
    email="alice@example.org",
)

_STAFF_CALLER = Actor(
    id=PermissionId("permission-staff"),
    group=GroupName.CURATORIAL,
    email="staff@example.org",
)


def _permission_record(permission_id: str, group_name: GroupName) -> PermissionRecord:
    user_id = f"user-{permission_id}"
    group_id = f"group-{group_name.value}"
    record = PermissionRecord(id=permission_id, user_id=user_id, group_id=group_id)
    record.user = UserRecord(
        id=user_id,
        name=f"User {permission_id}",
        email=f"{permission_id}@example.org",
        password_hash="",
    )
    record.group = GroupRecord(id=group_id, name=group_name)
    return record


def _proposal(
    proposal_id: str = "prop-1",
    requested_by: PermissionId | None = None,
    status: ProposalStatus = ProposalStatus.PENDING,
    documents: list[Document] | None = None,
) -> Proposal:
    requested_by = requested_by or PermissionId("permission-1")
    return Proposal(
        id=ProposalId(proposal_id),
        reference_number=ReferenceNumber("VRP-20260601-0001"),
        title="Proposal title",
        collection_use_project_id=CollectionUseProjectId("proj-1"),
        intended_use=UseType.IN_SITU_VISIT,
        begin_date=date(2026, 6, 1),
        end_date=date(2026, 6, 7),
        status=status,
        requested_by=requested_by,
        submitted_at=datetime(2026, 6, 7, tzinfo=UTC),
        documents=documents or [],
    )


def _collection_use_object(
    object_id: str = "cuo-1", inventory_number: str = "INV-001"
) -> CollectionUseObject:
    return CollectionUseObject(
        id=CollectionUseObjectId(object_id),
        inventory_number=inventory_number,
        category="fox head",
        description="a fox head",
        requested_at=datetime(2026, 6, 1, tzinfo=UTC),
        requested_by=PermissionId("permission-1"),
    )


def _project(
    project_id: str = "proj-1",
    requested_by: PermissionId | None = None,
    status: UseStatus = UseStatus.CREATED,
    objects: list[CollectionUseObject] | None = None,
) -> CollectionUseProject:
    requested_by = requested_by or PermissionId("permission-1")
    return CollectionUseProject(
        id=CollectionUseProjectId(project_id),
        reference_number=ReferenceNumber("CUP-ABCDEFG1"),
        title="Project title",
        purpose="Use collection",
        intended_use=UseType.IN_SITU_VISIT,
        status=status,
        begin_date=date(2026, 6, 1),
        end_date=date(2026, 6, 7),
        requested_by=requested_by,
        proposal_id=ProposalId("prop-1"),
        objects=objects if objects is not None else [],
    )


class InMemoryProjectRepository:
    def __init__(self) -> None:
        self.items: dict[str, CollectionUseProject] = {}

    async def add(self, project: CollectionUseProject) -> None:
        self.items[project.id] = project

    async def get_by_id(self, project_id: str) -> CollectionUseProject | None:
        return self.items.get(project_id)

    async def get_by_reference(
        self, ref: ReferenceNumber
    ) -> CollectionUseProject | None:
        return next((p for p in self.items.values() if p.reference_number == ref), None)

    async def save(self, project: CollectionUseProject) -> None:
        self.items[project.id] = project

    async def list(self, filters: ProjectFilters, page: int, size: int):
        items = list(self.items.values())
        if filters.status:
            items = [item for item in items if item.status == filters.status]
        if filters.use_type:
            items = [item for item in items if item.intended_use == filters.use_type]
        if filters.requested_by:
            items = [
                item for item in items if item.requested_by == filters.requested_by
            ]
        if filters.date_from:
            items = [item for item in items if item.begin_date >= filters.date_from]
        if filters.date_to:
            items = [item for item in items if item.begin_date <= filters.date_to]
        if filters.search:
            pattern = filters.search.lower()
            items = [
                item
                for item in items
                if pattern in item.title.lower()
                or pattern in item.reference_number.value.lower()
            ]
        return items[page * size : page * size + size], len(items)


class InMemoryProposalRepository:
    def __init__(self) -> None:
        self.items: dict[str, Proposal] = {}
        self.project_lookup_count = 0

    async def add(self, proposal: Proposal) -> None:
        self.items[proposal.id] = proposal

    async def next_reference_number_for(self, day: date) -> ReferenceNumber:
        prefix = f"VRP-{day:%Y%m%d}-"
        latest = max(
            (
                proposal.reference_number.value
                for proposal in self.items.values()
                if proposal.reference_number.value.startswith(prefix)
            ),
            default=None,
        )
        sequence = int(latest.removeprefix(prefix)) + 1 if latest else 1
        return ReferenceNumber(f"{prefix}{sequence:04d}")

    async def get_by_id(self, proposal_id: ProposalId) -> Proposal | None:
        return self.items.get(proposal_id)

    async def get_by_project_id(
        self, project_id: CollectionUseProjectId
    ) -> Proposal | None:
        self.project_lookup_count += 1
        return next(
            (
                proposal
                for proposal in self.items.values()
                if proposal.collection_use_project_id == project_id
            ),
            None,
        )

    async def list_by_project_ids(
        self, project_ids: list[CollectionUseProjectId]
    ) -> list[Proposal]:
        self.project_lookup_count += 1
        project_id_set = set(project_ids)
        return [
            proposal
            for proposal in self.items.values()
            if proposal.collection_use_project_id in project_id_set
        ]

    async def save(self, proposal: Proposal) -> None:
        self.items[proposal.id] = proposal

    async def list(self, filters: ProposalFilters, page: int, size: int):
        if size == 10000:
            raise AssertionError("Use targeted project proposal lookup instead")
        items = list(self.items.values())
        if filters.statuses:
            items = [item for item in items if item.status in filters.statuses]
        return items[page * size : page * size + size], len(items)


class InMemoryConversationRepository:
    def __init__(self) -> None:
        self.items: dict[str, Conversation] = {}

    async def add(self, conversation: Conversation) -> None:
        self.items[conversation.proposal_id] = conversation

    async def get_by_proposal_id(self, proposal_id: ProposalId) -> Conversation | None:
        return self.items.get(proposal_id)

    async def save(self, conversation: Conversation) -> None:
        self.items[conversation.proposal_id] = conversation


class InMemoryAccessLogRepository:
    def __init__(self) -> None:
        self.items: dict[str, ObjectAccessLog] = {}
        self.entries: dict[str, ObjectLogEntry] = {}

    async def add(self, access_log: ObjectAccessLog) -> None:
        self.items[access_log.id] = access_log

    async def get_by_id(self, access_log_id) -> ObjectAccessLog | None:
        return self.items.get(access_log_id)

    async def get_by_project_id(self, project_id) -> ObjectAccessLog | None:
        for access_log in self.items.values():
            if access_log.collection_use_project_id == project_id:
                return access_log
        return None

    async def get_entry_by_id(self, entry_id) -> ObjectLogEntry | None:
        return self.entries.get(entry_id)

    async def save(self, access_log: ObjectAccessLog) -> None:
        self.items[access_log.id] = access_log

    async def save_entry(self, entry: ObjectLogEntry) -> None:
        self.entries[entry.id] = entry

    async def list_entries_by_project(self, project_id, added_by, page, size):
        log_ids = {
            log.id
            for log in self.items.values()
            if log.collection_use_project_id == project_id
        }
        items = [
            entry
            for entry in self.entries.values()
            if entry.object_access_log_id in log_ids
            and (added_by is None or entry.added_by == added_by)
        ]
        return items[page * size : page * size + size], len(items)


class InMemoryOccurrenceLogRepository:
    def __init__(self) -> None:
        self.items: dict[str, ObjectOccurrenceLog] = {}
        self.entries: dict[str, ObjectOccurrenceEntry] = {}

    async def add(self, occurrence_log: ObjectOccurrenceLog) -> None:
        self.items[occurrence_log.id] = occurrence_log

    async def get_by_id(self, occurrence_log_id) -> ObjectOccurrenceLog | None:
        return self.items.get(occurrence_log_id)

    async def get_by_project_id(self, project_id) -> ObjectOccurrenceLog | None:
        for occurrence_log in self.items.values():
            if occurrence_log.collection_use_project_id == project_id:
                return occurrence_log
        return None

    async def get_entry_by_id(self, entry_id) -> ObjectOccurrenceEntry | None:
        return self.entries.get(entry_id)

    async def save(self, occurrence_log: ObjectOccurrenceLog) -> None:
        self.items[occurrence_log.id] = occurrence_log

    async def save_entry(self, entry: ObjectOccurrenceEntry) -> None:
        self.entries[entry.id] = entry

    async def list_entries_by_project(self, project_id, reported_by, page, size):
        log_ids = {
            log.id
            for log in self.items.values()
            if log.collection_use_project_id == project_id
        }
        items = [
            entry
            for entry in self.entries.values()
            if entry.object_occurrence_log_id in log_ids
            and (reported_by is None or entry.reported_by == reported_by)
        ]
        return items[page * size : page * size + size], len(items)


class InMemoryPublicationLogRepository:
    def __init__(self) -> None:
        self.items: dict[str, PublicationLog] = {}
        self.entries: dict[str, PublicationLogEntry] = {}

    async def add(self, publication_log: PublicationLog) -> None:
        self.items[publication_log.id] = publication_log

    async def get_by_id(self, publication_log_id) -> PublicationLog | None:
        return self.items.get(publication_log_id)

    async def get_by_project_id(self, project_id) -> PublicationLog | None:
        for publication_log in self.items.values():
            if publication_log.collection_use_project_id == project_id:
                return publication_log
        return None

    async def get_entry_by_id(self, entry_id) -> PublicationLogEntry | None:
        return self.entries.get(entry_id)

    async def save(self, publication_log: PublicationLog) -> None:
        self.items[publication_log.id] = publication_log

    async def save_entry(self, entry: PublicationLogEntry) -> None:
        self.entries[entry.id] = entry

    async def list_entries_by_project(self, project_id, added_by, page, size):
        log_ids = {
            log.id
            for log in self.items.values()
            if log.collection_use_project_id == project_id
        }
        items = [
            entry
            for entry in self.entries.values()
            if entry.publication_log_id in log_ids
            and (added_by is None or entry.added_by == added_by)
        ]
        return items[page * size : page * size + size], len(items)


class InMemoryFileStorage:
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}

    async def save(self, content: bytes, filename: str) -> str:
        self.files[filename] = content
        return filename

    async def read(self, file_reference: str) -> bytes:
        try:
            return self.files[file_reference]
        except KeyError as exc:
            raise FileNotFoundError(file_reference) from exc


class CommitOnlySession:
    def __init__(
        self, permission_records: dict[str, PermissionRecord] | None = None
    ) -> None:
        self._permission_records = permission_records or {}

    async def commit(self) -> None:
        return None

    def begin_nested(self):
        # No-op savepoint for run_with_unique_retry; the in-memory repos enforce
        # no constraints, so the operation simply runs once.
        @asynccontextmanager
        async def _noop() -> AsyncIterator[None]:
            yield

        return _noop()

    async def get(self, model, pk, **kwargs):
        if model is PermissionRecord:
            return self._permission_records.get(str(pk))
        return None

    async def execute(self, *args, **kwargs):
        class FakeResult:
            def scalar_one_or_none(self):
                return None

            def scalar_one(self):
                return 0

            def scalars(self):
                class S:
                    def all(self):
                        return []

                return S()

        return FakeResult()


class RecordingRequesterProvisioner:
    """Fake ``ExternalRequesterProvisioner``. Raises if invoked with no
    ``resolved`` configured, so route tests approving an already-resolved
    proposal catch an unexpected (unnecessary) provisioning call."""

    def __init__(self, resolved: ResolvedExternalRequester | None = None) -> None:
        self._resolved = resolved
        self.calls: list[tuple[str, str]] = []

    async def provision(self, email: str, name: str) -> ResolvedExternalRequester:
        self.calls.append((email, name))
        if self._resolved is None:
            raise AssertionError("provision() should not have been called")
        return self._resolved


class RecordingAccessEmailSender:
    """Fake ``RequesterAccessEmailSender`` recording every call it receives."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str, str]] = []

    async def send_access_created(
        self,
        to_email: str,
        requester_name: str,
        login_url: str,
        temporary_password: str,
    ) -> None:
        self.calls.append((to_email, requester_name, login_url, temporary_password))


@asynccontextmanager
async def client_with_repos(
    caller: Actor = _CALLER,
    permission_records: dict[str, PermissionRecord] | None = None,
    requester_provisioner: RecordingRequesterProvisioner | None = None,
    access_email_sender: RecordingAccessEmailSender | None = None,
) -> AsyncIterator[
    tuple[
        AsyncClient,
        InMemoryProjectRepository,
        InMemoryProposalRepository,
        InMemoryConversationRepository,
    ]
]:
    project_repo = InMemoryProjectRepository()
    proposal_repo = InMemoryProposalRepository()
    conversation_repo = InMemoryConversationRepository()
    access_log_repo = InMemoryAccessLogRepository()
    occurrence_log_repo = InMemoryOccurrenceLogRepository()
    publication_log_repo = InMemoryPublicationLogRepository()
    file_storage = InMemoryFileStorage()
    session = CommitOnlySession(permission_records)
    requester_provisioner = requester_provisioner or RecordingRequesterProvisioner()
    access_email_sender = access_email_sender or RecordingAccessEmailSender()

    app.dependency_overrides[get_project_repo] = lambda: project_repo
    app.dependency_overrides[get_proposal_repo] = lambda: proposal_repo
    app.dependency_overrides[get_conversation_repo] = lambda: conversation_repo
    app.dependency_overrides[get_access_log_repo] = lambda: access_log_repo
    app.dependency_overrides[get_occurrence_log_repo] = lambda: occurrence_log_repo
    app.dependency_overrides[get_publication_log_repo] = lambda: publication_log_repo
    app.dependency_overrides[get_file_storage] = lambda: file_storage
    app.dependency_overrides[get_async_session] = lambda: session
    app.dependency_overrides[get_caller_permission] = lambda: caller
    app.dependency_overrides[get_external_requester_provisioner] = lambda: (
        requester_provisioner
    )
    app.dependency_overrides[get_requester_access_email_sender] = lambda: (
        access_email_sender
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, project_repo, proposal_repo, conversation_repo

    app.dependency_overrides.clear()


async def test_submit_proposal_returns_201() -> None:
    async with client_with_repos() as (client, _, _, _):
        response = await client.post(
            "/api/v1/proposals",
            json={
                "title": "Collection study",
                "intendedUse": "IN_SITU_VISIT",
                "purpose": "To study the collection",
                "beginDate": "2026-06-01",
                "endDate": "2026-06-07",
            },
            headers={"X-Permission-Id": "permission-1"},
        )

    assert response.status_code == 201
    body = response.json()
    assert body["proposal"]["status"] == "SUBMITTED"
    assert body["proposal"]["referenceNumber"].startswith("VRP-")
    assert body["proposal"]["title"] == "Collection study"
    assert body["proposal"]["beginDate"] == "2026-06-01"
    assert body["proposal"]["endDate"] == "2026-06-07"
    assert "conversationId" in body


async def test_submit_proposal_carries_intended_use_through_to_detail() -> None:
    async with client_with_repos() as (client, _, _, _):
        created = await client.post(
            "/api/v1/proposals",
            json={
                "title": "Collection study",
                "intendedUse": "EXHIBITION",
                "purpose": "To exhibit the collection",
                "beginDate": "2026-06-01",
                "endDate": "2026-06-07",
            },
            headers={"X-Permission-Id": "permission-1"},
        )
        proposal_id = created.json()["proposal"]["id"]
        detail = await client.get(
            f"/api/v1/proposals/{proposal_id}",
            headers={"X-Permission-Id": "permission-1"},
        )

    assert created.status_code == 201
    assert created.json()["proposal"]["intendedUse"] == "EXHIBITION"
    # The use type survives the round-trip through the repository.
    assert detail.status_code == 200
    assert detail.json()["intendedUse"] == "EXHIBITION"


async def test_submit_proposal_invalid_date_range_returns_422() -> None:
    async with client_with_repos() as (client, _, _, _):
        response = await client.post(
            "/api/v1/proposals",
            json={
                "title": "Collection study",
                "intendedUse": "IN_SITU_VISIT",
                "purpose": "To study the collection",
                "beginDate": "2026-06-07",
                "endDate": "2026-06-01",
            },
            headers={"X-Permission-Id": "permission-1"},
        )

    assert response.status_code == 422
    assert response.json()["message"] == "endDate must be after beginDate"


async def test_list_proposals_serializes_populated_item() -> None:
    async with client_with_repos() as (client, _, proposal_repo, _):
        await proposal_repo.add(
            Proposal(
                id=ProposalId("prop-1"),
                reference_number=ReferenceNumber("VRP-20260601-0001"),
                title="Proposal title",
                collection_use_project_id="proj-1",
                intended_use=UseType.IN_SITU_VISIT,
                begin_date=date(2026, 6, 1),
                end_date=date(2026, 6, 7),
                status=ProposalStatus.SUBMITTED,
                requested_by=PermissionId("permission-1"),
                submitted_at=datetime(2026, 6, 7, tzinfo=UTC),
            )
        )

        response = await client.get(
            "/api/v1/proposals",
            headers={"X-Permission-Id": "permission-1"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["totalElements"] == 1
    item = body["content"][0]
    assert item["id"] == "prop-1"
    assert item["referenceNumber"] == "VRP-20260601-0001"
    assert item["title"] == "Proposal title"
    assert item["status"] == "SUBMITTED"
    assert item["intendedUse"] == "IN_SITU_VISIT"


async def test_list_proposals_paginates_results() -> None:
    async with client_with_repos() as (client, _, proposal_repo, _):
        for index in range(3):
            await proposal_repo.add(
                Proposal(
                    id=ProposalId(f"prop-{index + 1}"),
                    reference_number=ReferenceNumber(f"VRP-20260601-{index + 1:04d}"),
                    title=f"Proposal {index + 1}",
                    collection_use_project_id=CollectionUseProjectId(
                        f"proj-{index + 1}"
                    ),
                    intended_use=UseType.IN_SITU_VISIT,
                    begin_date=date(2026, 6, 1),
                    end_date=date(2026, 6, 7),
                    status=ProposalStatus.SUBMITTED,
                    requested_by=PermissionId("permission-1"),
                    submitted_at=datetime(2026, 6, 7, index, tzinfo=UTC),
                )
            )

        response = await client.get(
            "/api/v1/proposals?page=1&size=2",
            headers={"X-Permission-Id": "permission-1"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["page"] == 1
    assert body["size"] == 2
    assert body["totalElements"] == 3
    assert body["totalPages"] == 2
    assert [item["id"] for item in body["content"]] == ["prop-3"]


async def test_list_proposals_filters_by_multiple_statuses() -> None:
    async with client_with_repos() as (client, _, proposal_repo, _):
        for proposal_id, status in (
            ("rejected", ProposalStatus.REJECTED),
            ("cancelled", ProposalStatus.CANCELLED),
            ("pending", ProposalStatus.PENDING),
        ):
            proposal = _proposal(proposal_id=proposal_id, status=status)
            proposal.reference_number = ReferenceNumber(
                f"VRP-20260601-{len(proposal_repo.items) + 1:04d}"
            )
            await proposal_repo.add(proposal)

        response = await client.get(
            "/api/v1/proposals?status=REJECTED&status=CANCELLED&page=0&size=100",
            headers={"X-Permission-Id": "permission-1"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["totalElements"] == 2
    assert {item["status"] for item in body["content"]} == {
        "REJECTED",
        "CANCELLED",
    }


async def test_get_proposal_not_found_returns_404() -> None:
    async with client_with_repos() as (client, _, _, _):
        response = await client.get(
            "/api/v1/proposals/nonexistent-id",
            headers={"X-Permission-Id": "permission-1"},
        )

    assert response.status_code == 404


async def test_relate_searched_objects_surfaces_them_on_detail() -> None:
    # A proposal is created object-free; the researcher later searches the
    # catalog and relates the matches via POST /requested-objects, supplying the
    # full inventory snapshot from the search result.
    async with client_with_repos() as (client, _, proposal_repo, _):
        create = await client.post(
            "/api/v1/proposals",
            json={
                "title": "Manuscript study",
                "intendedUse": "IN_SITU_VISIT",
                "purpose": "To study the manuscript",
                "beginDate": "2026-06-01",
                "endDate": "2026-06-07",
            },
            headers={"X-Permission-Id": "permission-1"},
        )
        assert create.status_code == 201
        proposal_id = create.json()["proposal"]["id"]

        related = await client.post(
            f"/api/v1/proposals/{proposal_id}/requested-objects",
            json={
                "objects": [
                    {
                        "inventoryNumber": "INV-001",
                        "displayTitle": "Book of Hours",
                        "objectName": "Illuminated manuscript",
                        "category": "manuscript",
                    }
                ]
            },
            headers={"X-Permission-Id": "permission-1"},
        )
        assert related.status_code == 201

        detail = await client.get(
            f"/api/v1/proposals/{proposal_id}",
            headers={"X-Permission-Id": "permission-1"},
        )

    assert detail.status_code == 200
    body = detail.json()
    assert body["referenceNumber"].startswith("VRP-")
    assert body["title"] == "Manuscript study"
    objects = body["requestedObjects"]
    assert len(objects) == 1
    assert objects[0]["inventoryNumber"] == "INV-001"
    assert objects[0]["displayTitle"] == "Book of Hours"
    assert objects[0]["objectName"] == "Illuminated manuscript"
    assert objects[0]["category"] == "manuscript"


async def test_remove_requested_object_updates_proposal_detail() -> None:
    async with client_with_repos() as (client, _, _, _):
        create = await client.post(
            "/api/v1/proposals",
            json={
                "title": "Manuscript study",
                "intendedUse": "IN_SITU_VISIT",
                "purpose": "To study the manuscript",
                "beginDate": "2026-06-01",
                "endDate": "2026-06-07",
            },
            headers={"X-Permission-Id": "permission-1"},
        )
        assert create.status_code == 201
        proposal_id = create.json()["proposal"]["id"]

        related = await client.post(
            f"/api/v1/proposals/{proposal_id}/requested-objects",
            json={
                "objects": [
                    {
                        "inventoryNumber": "INV-001",
                        "displayTitle": "Book of Hours",
                        "objectName": "Illuminated manuscript",
                    }
                ]
            },
            headers={"X-Permission-Id": "permission-1"},
        )
        assert related.status_code == 201
        requested_object_id = related.json()["requestedObjects"][0]["id"]

        removed = await client.delete(
            f"/api/v1/proposals/{proposal_id}/requested-objects/{requested_object_id}",
            headers={"X-Permission-Id": "permission-1"},
        )
        detail = await client.get(
            f"/api/v1/proposals/{proposal_id}",
            headers={"X-Permission-Id": "permission-1"},
        )

    assert removed.status_code == 204
    assert detail.status_code == 200
    assert detail.json()["requestedObjects"] == []


async def test_external_user_cannot_read_other_proposal_events() -> None:
    async with client_with_repos() as (client, _, proposal_repo, _):
        await proposal_repo.add(
            Proposal(
                id=ProposalId("prop-foreign"),
                reference_number=ReferenceNumber("VRP-20260601-0001"),
                title="Proposal title",
                collection_use_project_id=CollectionUseProjectId("proj-foreign"),
                intended_use=UseType.IN_SITU_VISIT,
                begin_date=date(2026, 6, 1),
                end_date=date(2026, 6, 7),
                status=ProposalStatus.SUBMITTED,
                requested_by=PermissionId("permission-other"),
                submitted_at=datetime(2026, 6, 7, tzinfo=UTC),
            )
        )

        response = await client.get(
            "/api/v1/proposals/prop-foreign/events",
            headers={"X-Permission-Id": "permission-1"},
        )

    assert response.status_code == 403
    assert response.json()["error"] == "ACCESS_DENIED"


async def test_external_user_cannot_read_other_proposal_documents() -> None:
    async with client_with_repos() as (client, _, proposal_repo, _):
        await proposal_repo.add(
            Proposal(
                id=ProposalId("prop-foreign"),
                reference_number=ReferenceNumber("VRP-20260601-0001"),
                title="Proposal title",
                collection_use_project_id=CollectionUseProjectId("proj-foreign"),
                intended_use=UseType.IN_SITU_VISIT,
                begin_date=date(2026, 6, 1),
                end_date=date(2026, 6, 7),
                status=ProposalStatus.SUBMITTED,
                requested_by=PermissionId("permission-other"),
                submitted_at=datetime(2026, 6, 7, tzinfo=UTC),
            )
        )

        response = await client.get(
            "/api/v1/proposals/prop-foreign/documents",
            headers={"X-Permission-Id": "permission-1"},
        )

    assert response.status_code == 403
    assert response.json()["error"] == "ACCESS_DENIED"


async def test_external_user_cannot_read_other_project_events() -> None:
    async with client_with_repos() as (client, project_repo, proposal_repo, _):
        await project_repo.add(
            CollectionUseProject(
                id=CollectionUseProjectId("proj-foreign"),
                reference_number=ReferenceNumber("CUP-ABCDEFG1"),
                title="Foreign project",
                purpose="Restricted",
                intended_use=UseType.IN_SITU_VISIT,
                status=UseStatus.CREATED,
                begin_date=date(2026, 6, 1),
                end_date=date(2026, 6, 7),
                requested_by=PermissionId("permission-other"),
            )
        )
        await proposal_repo.add(
            Proposal(
                id=ProposalId("prop-foreign"),
                reference_number=ReferenceNumber("VRP-20260601-0001"),
                title="Proposal title",
                collection_use_project_id=CollectionUseProjectId("proj-foreign"),
                intended_use=UseType.IN_SITU_VISIT,
                begin_date=date(2026, 6, 1),
                end_date=date(2026, 6, 7),
                status=ProposalStatus.APPROVED,
                requested_by=PermissionId("permission-other"),
                submitted_at=datetime(2026, 6, 7, tzinfo=UTC),
            )
        )

        response = await client.get(
            "/api/v1/collection-use-projects/proj-foreign/events",
            headers={"X-Permission-Id": "permission-1"},
        )

    assert response.status_code == 403
    assert response.json()["error"] == "ACCESS_DENIED"


async def test_list_projects_applies_search_filter() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        project_repo,
        _,
        _,
    ):
        await project_repo.add(
            CollectionUseProject(
                id=CollectionUseProjectId("project-alpha"),
                reference_number=ReferenceNumber("CUP-ALPHA001"),
                title="Alpha manuscripts",
                purpose="Visible",
                intended_use=UseType.IN_SITU_VISIT,
                status=UseStatus.CREATED,
                begin_date=date(2026, 6, 1),
                end_date=date(2026, 6, 7),
                requested_by=PermissionId("permission-1"),
            )
        )
        await project_repo.add(
            CollectionUseProject(
                id=CollectionUseProjectId("project-beta"),
                reference_number=ReferenceNumber("CUP-BETA0001"),
                title="Beta paintings",
                purpose="Hidden by search",
                intended_use=UseType.IN_SITU_VISIT,
                status=UseStatus.CREATED,
                begin_date=date(2026, 6, 1),
                end_date=date(2026, 6, 7),
                requested_by=PermissionId("permission-1"),
            )
        )

        response = await client.get("/api/v1/collection-use-projects?search=alpha")

    assert response.status_code == 200
    body = response.json()
    assert body["totalElements"] == 1
    assert body["content"][0]["id"] == "project-alpha"


async def test_staff_can_scope_list_with_requested_by() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        project_repo,
        _,
        _,
    ):
        await project_repo.add(
            _project("mine", requested_by=PermissionId("permission-staff"))
        )
        await project_repo.add(
            _project("theirs", requested_by=PermissionId("permission-other"))
        )

        scoped = await client.get(
            "/api/v1/collection-use-projects?requestedBy=permission-staff",
            headers={"X-Permission-Id": "permission-staff"},
        )
        unscoped = await client.get(
            "/api/v1/collection-use-projects",
            headers={"X-Permission-Id": "permission-staff"},
        )

    assert scoped.status_code == 200
    scoped_body = scoped.json()
    assert scoped_body["totalElements"] == 1
    assert scoped_body["content"][0]["id"] == "mine"
    # Without the filter, staff still see every project.
    assert unscoped.json()["totalElements"] == 2


async def test_non_staff_requested_by_is_ignored_and_forced_to_own_id() -> None:
    async with client_with_repos(caller=_CALLER) as (
        client,
        project_repo,
        _,
        _,
    ):
        await project_repo.add(
            _project("mine", requested_by=PermissionId("permission-1"))
        )
        await project_repo.add(
            _project("theirs", requested_by=PermissionId("permission-other"))
        )

        # A non-staff caller tries to see someone else's projects.
        response = await client.get(
            "/api/v1/collection-use-projects?requestedBy=permission-other",
            headers={"X-Permission-Id": "permission-1"},
        )

    assert response.status_code == 200
    body = response.json()
    # The spoofed filter is ignored; the list stays scoped to the caller's id.
    assert body["totalElements"] == 1
    assert body["content"][0]["id"] == "mine"


async def test_list_projects_applies_date_filters() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        project_repo,
        _,
        _,
    ):
        await project_repo.add(
            CollectionUseProject(
                id=CollectionUseProjectId("project-june"),
                reference_number=ReferenceNumber("CUP-JUNE0001"),
                title="June project",
                purpose="Visible",
                intended_use=UseType.IN_SITU_VISIT,
                status=UseStatus.CREATED,
                begin_date=date(2026, 6, 10),
                end_date=date(2026, 6, 12),
                requested_by=PermissionId("permission-1"),
            )
        )
        await project_repo.add(
            CollectionUseProject(
                id=CollectionUseProjectId("project-july"),
                reference_number=ReferenceNumber("CUP-JULY0001"),
                title="July project",
                purpose="Hidden by dates",
                intended_use=UseType.IN_SITU_VISIT,
                status=UseStatus.CREATED,
                begin_date=date(2026, 7, 10),
                end_date=date(2026, 7, 12),
                requested_by=PermissionId("permission-1"),
            )
        )

        response = await client.get(
            "/api/v1/collection-use-projects?dateFrom=2026-06-01&dateTo=2026-06-30"
        )

    assert response.status_code == 200
    body = response.json()
    assert body["totalElements"] == 1
    assert body["content"][0]["id"] == "project-june"


async def test_external_owner_cannot_assign_proposal() -> None:
    async with client_with_repos() as (client, _, proposal_repo, _):
        await proposal_repo.add(
            Proposal(
                id=ProposalId("prop-1"),
                reference_number=ReferenceNumber("VRP-20260601-0001"),
                title="Proposal title",
                collection_use_project_id=CollectionUseProjectId("proj-1"),
                intended_use=UseType.IN_SITU_VISIT,
                begin_date=date(2026, 6, 1),
                end_date=date(2026, 6, 7),
                status=ProposalStatus.SUBMITTED,
                requested_by=PermissionId("permission-1"),
                submitted_at=datetime(2026, 6, 7, tzinfo=UTC),
            )
        )

        response = await client.post(
            "/api/v1/proposals/prop-1/assign",
            json={},
            headers={"X-Permission-Id": "permission-1"},
        )

    assert response.status_code == 403
    assert response.json()["error"] == "INSUFFICIENT_GROUP"


async def test_external_owner_cannot_request_documents() -> None:
    async with client_with_repos() as (client, _, proposal_repo, _):
        await proposal_repo.add(
            Proposal(
                id=ProposalId("prop-1"),
                reference_number=ReferenceNumber("VRP-20260601-0001"),
                title="Proposal title",
                collection_use_project_id=CollectionUseProjectId("proj-1"),
                intended_use=UseType.IN_SITU_VISIT,
                begin_date=date(2026, 6, 1),
                end_date=date(2026, 6, 7),
                status=ProposalStatus.PENDING,
                requested_by=PermissionId("permission-1"),
                submitted_at=datetime(2026, 6, 7, tzinfo=UTC),
            )
        )

        response = await client.post(
            "/api/v1/proposals/prop-1/request-documents",
            json={
                "requiredDocuments": [
                    {"type": "insurance", "description": "Insurance proof"}
                ]
            },
            headers={"X-Permission-Id": "permission-1"},
        )

    assert response.status_code == 403
    assert response.json()["error"] == "INSUFFICIENT_GROUP"


async def test_assign_proposal_rejects_unknown_target_permission() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        _,
        proposal_repo,
        _,
    ):
        await proposal_repo.add(
            Proposal(
                id=ProposalId("prop-1"),
                reference_number=ReferenceNumber("VRP-20260601-0001"),
                title="Proposal title",
                collection_use_project_id=CollectionUseProjectId("proj-1"),
                intended_use=UseType.IN_SITU_VISIT,
                begin_date=date(2026, 6, 1),
                end_date=date(2026, 6, 7),
                status=ProposalStatus.SUBMITTED,
                requested_by=PermissionId("permission-1"),
                submitted_at=datetime(2026, 6, 7, tzinfo=UTC),
            )
        )

        response = await client.post(
            "/api/v1/proposals/prop-1/assign",
            json={"targetPermissionId": "missing-permission"},
        )

    assert response.status_code == 404
    assert response.json()["error"] == "PERMISSION_NOT_FOUND"


async def test_assign_proposal_rejects_external_target_permission() -> None:
    async with client_with_repos(
        caller=_STAFF_CALLER,
        permission_records={
            "permission-external": _permission_record(
                "permission-external", GroupName.EXTERNAL
            )
        },
    ) as (client, _, proposal_repo, _):
        await proposal_repo.add(
            Proposal(
                id=ProposalId("prop-1"),
                reference_number=ReferenceNumber("VRP-20260601-0001"),
                title="Proposal title",
                collection_use_project_id=CollectionUseProjectId("proj-1"),
                intended_use=UseType.IN_SITU_VISIT,
                begin_date=date(2026, 6, 1),
                end_date=date(2026, 6, 7),
                status=ProposalStatus.SUBMITTED,
                requested_by=PermissionId("permission-1"),
                submitted_at=datetime(2026, 6, 7, tzinfo=UTC),
            )
        )

        response = await client.post(
            "/api/v1/proposals/prop-1/assign",
            json={"targetPermissionId": "permission-external"},
        )

    assert response.status_code == 422
    assert response.json()["error"] == "INVALID_PERMISSION_TARGET"


async def test_forward_proposal_rejects_external_target_permission() -> None:
    async with client_with_repos(
        caller=_STAFF_CALLER,
        permission_records={
            "permission-external": _permission_record(
                "permission-external", GroupName.EXTERNAL
            )
        },
    ) as (client, _, proposal_repo, _):
        await proposal_repo.add(
            Proposal(
                id=ProposalId("prop-1"),
                reference_number=ReferenceNumber("VRP-20260601-0001"),
                title="Proposal title",
                collection_use_project_id=CollectionUseProjectId("proj-1"),
                intended_use=UseType.IN_SITU_VISIT,
                begin_date=date(2026, 6, 1),
                end_date=date(2026, 6, 7),
                status=ProposalStatus.PENDING,
                requested_by=PermissionId("permission-1"),
                submitted_at=datetime(2026, 6, 7, tzinfo=UTC),
            )
        )

        response = await client.post(
            "/api/v1/proposals/prop-1/forward",
            json={"targetPermissionId": "permission-external"},
        )

    assert response.status_code == 422
    assert response.json()["error"] == "INVALID_PERMISSION_TARGET"


async def test_reject_proposal_creates_message_to_requester() -> None:
    async with client_with_repos(
        caller=_STAFF_CALLER,
        permission_records={
            "permission-1": _permission_record("permission-1", GroupName.EXTERNAL)
        },
    ) as (client, _, proposal_repo, conversation_repo):
        proposal = Proposal(
            id=ProposalId("prop-1"),
            reference_number=ReferenceNumber("VRP-20260601-0001"),
            title="Proposal title",
            collection_use_project_id=CollectionUseProjectId("proj-1"),
            intended_use=UseType.IN_SITU_VISIT,
            begin_date=date(2026, 6, 1),
            end_date=date(2026, 6, 7),
            status=ProposalStatus.PENDING,
            requested_by=PermissionId("permission-1"),
            submitted_at=datetime(2026, 6, 7, tzinfo=UTC),
        )
        await proposal_repo.add(proposal)
        await conversation_repo.add(
            Conversation.start(
                id=ConversationId("conv-1"),
                proposal_id=proposal.id,
                initial_message=Message(
                    id=MessageId("message-1"),
                    sent_at=datetime(2026, 6, 7, tzinfo=UTC),
                    sender=EmailAddress("permission-1@example.org"),
                    recipient=EmailAddress("collections@museum.pt"),
                    subject="Initial",
                    body="Initial message",
                ),
            )
        )

        response = await client.post(
            "/api/v1/proposals/prop-1/reject",
            json={"reason": "The request is outside the collection policy."},
        )
        saved_conversation = await conversation_repo.get_by_proposal_id(proposal.id)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "REJECTED"
    assert saved_conversation is not None
    message = saved_conversation.messages[-1]
    assert message.sender.value == "staff@example.org"
    assert message.recipient.value == "permission-1@example.org"
    assert message.body == "The request is outside the collection policy."


async def test_staff_can_assign_proposal_to_staff_target() -> None:
    async with client_with_repos(
        caller=_STAFF_CALLER,
        permission_records={
            "permission-staff": _permission_record(
                "permission-staff", GroupName.CURATORIAL
            ),
            "permission-target": _permission_record(
                "permission-target", GroupName.COLLECTIONS_MANAGEMENT
            ),
        },
    ) as (client, _, proposal_repo, _):
        await proposal_repo.add(
            Proposal(
                id=ProposalId("prop-1"),
                reference_number=ReferenceNumber("VRP-20260601-0001"),
                title="Proposal title",
                collection_use_project_id=CollectionUseProjectId("proj-1"),
                intended_use=UseType.IN_SITU_VISIT,
                begin_date=date(2026, 6, 1),
                end_date=date(2026, 6, 7),
                status=ProposalStatus.SUBMITTED,
                requested_by=PermissionId("permission-1"),
                submitted_at=datetime(2026, 6, 7, tzinfo=UTC),
            )
        )

        response = await client.post(
            "/api/v1/proposals/prop-1/assign",
            json={"targetPermissionId": "permission-target"},
        )
        proposal = await proposal_repo.get_by_id(ProposalId("prop-1"))

    assert response.status_code == 200
    body = response.json()
    assert body["assignedTo"]["permissionId"] == "permission-target"
    assert body["lastEvent"]["triggeredBy"]["permissionId"] == "permission-staff"
    assert proposal is not None
    assert proposal.assigned_to == "permission-target"
    assert proposal.status == ProposalStatus.PENDING


async def test_staff_can_forward_proposal_to_staff_target() -> None:
    async with client_with_repos(
        caller=_STAFF_CALLER,
        permission_records={
            "permission-target": _permission_record(
                "permission-target", GroupName.DIRECTION
            )
        },
    ) as (client, _, proposal_repo, _):
        await proposal_repo.add(
            Proposal(
                id=ProposalId("prop-1"),
                reference_number=ReferenceNumber("VRP-20260601-0001"),
                title="Proposal title",
                collection_use_project_id=CollectionUseProjectId("proj-1"),
                intended_use=UseType.IN_SITU_VISIT,
                begin_date=date(2026, 6, 1),
                end_date=date(2026, 6, 7),
                status=ProposalStatus.PENDING,
                requested_by=PermissionId("permission-1"),
                submitted_at=datetime(2026, 6, 7, tzinfo=UTC),
            )
        )

        response = await client.post(
            "/api/v1/proposals/prop-1/forward",
            json={"targetPermissionId": "permission-target"},
        )
        proposal = await proposal_repo.get_by_id(ProposalId("prop-1"))

    assert response.status_code == 200
    assert response.json()["assignedTo"]["permissionId"] == "permission-target"
    assert proposal is not None
    assert proposal.assigned_to == "permission-target"


async def test_forward_proposal_rejects_non_pending_proposal() -> None:
    async with client_with_repos(
        caller=_STAFF_CALLER,
        permission_records={
            "permission-target": _permission_record(
                "permission-target", GroupName.DIRECTION
            )
        },
    ) as (client, _, proposal_repo, _):
        await proposal_repo.add(
            Proposal(
                id=ProposalId("prop-1"),
                reference_number=ReferenceNumber("VRP-20260601-0001"),
                title="Proposal title",
                collection_use_project_id=CollectionUseProjectId("proj-1"),
                intended_use=UseType.IN_SITU_VISIT,
                begin_date=date(2026, 6, 1),
                end_date=date(2026, 6, 7),
                status=ProposalStatus.APPROVED,
                requested_by=PermissionId("permission-1"),
                submitted_at=datetime(2026, 6, 7, tzinfo=UTC),
            )
        )

        response = await client.post(
            "/api/v1/proposals/prop-1/forward",
            json={"targetPermissionId": "permission-target"},
        )
        proposal = await proposal_repo.get_by_id(ProposalId("prop-1"))

    assert response.status_code == 409
    assert response.json()["error"] == "INVALID_TRANSITION"
    assert proposal is not None
    assert proposal.assigned_to is None


async def test_staff_can_patch_proposal_title() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        _,
        proposal_repo,
        _,
    ):
        await proposal_repo.add(_proposal())

        response = await client.patch(
            "/api/v1/proposals/prop-1",
            json={"title": "Corrected title"},
        )
        proposal = await proposal_repo.get_by_id(ProposalId("prop-1"))

    assert response.status_code == 200
    assert response.json()["title"] == "Corrected title"
    assert proposal is not None
    assert proposal.title == "Corrected title"


async def test_patch_proposal_null_title_clears_it() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        _,
        proposal_repo,
        _,
    ):
        await proposal_repo.add(_proposal())

        response = await client.patch(
            "/api/v1/proposals/prop-1",
            json={"title": None},
        )
        proposal = await proposal_repo.get_by_id(ProposalId("prop-1"))

    assert response.status_code == 200
    assert response.json()["title"] is None
    assert proposal is not None
    assert proposal.title is None


async def test_patch_proposal_omitted_fields_left_unchanged() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        _,
        proposal_repo,
        _,
    ):
        await proposal_repo.add(_proposal())

        response = await client.patch(
            "/api/v1/proposals/prop-1",
            json={"title": "Only the title"},
        )
        proposal = await proposal_repo.get_by_id(ProposalId("prop-1"))

    assert response.status_code == 200
    assert proposal is not None
    # Dates and intended use untouched by a title-only patch.
    assert proposal.begin_date == date(2026, 6, 1)
    assert proposal.end_date == date(2026, 6, 7)
    assert proposal.intended_use == UseType.IN_SITU_VISIT


async def test_patch_proposal_replaces_intended_use() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        _,
        proposal_repo,
        _,
    ):
        await proposal_repo.add(_proposal())

        response = await client.patch(
            "/api/v1/proposals/prop-1",
            json={"intendedUse": "IN_SITU_VISIT"},
        )
        proposal = await proposal_repo.get_by_id(ProposalId("prop-1"))

    assert response.status_code == 200
    assert proposal is not None
    assert proposal.intended_use == UseType.IN_SITU_VISIT


async def test_patch_proposal_clears_dates() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        _,
        proposal_repo,
        _,
    ):
        await proposal_repo.add(_proposal())

        response = await client.patch(
            "/api/v1/proposals/prop-1",
            json={"beginDate": None, "endDate": None},
        )
        proposal = await proposal_repo.get_by_id(ProposalId("prop-1"))

    assert response.status_code == 200
    body = response.json()
    assert body["beginDate"] is None
    assert body["endDate"] is None
    assert proposal is not None
    assert proposal.begin_date is None
    assert proposal.end_date is None


async def test_external_owner_cannot_patch_proposal() -> None:
    async with client_with_repos() as (client, _, proposal_repo, _):
        await proposal_repo.add(_proposal())

        response = await client.patch(
            "/api/v1/proposals/prop-1",
            json={"title": "Hijacked"},
            headers={"X-Permission-Id": "permission-1"},
        )
        proposal = await proposal_repo.get_by_id(ProposalId("prop-1"))

    assert response.status_code == 403
    assert response.json()["error"] == "INSUFFICIENT_GROUP"
    assert proposal is not None
    assert proposal.title == "Proposal title"


async def test_patch_proposal_terminal_status_returns_409() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        _,
        proposal_repo,
        _,
    ):
        await proposal_repo.add(_proposal(status=ProposalStatus.APPROVED))

        response = await client.patch(
            "/api/v1/proposals/prop-1",
            json={"title": "Too late"},
        )
        proposal = await proposal_repo.get_by_id(ProposalId("prop-1"))

    assert response.status_code == 409
    assert response.json()["error"] == "INVALID_TRANSITION"
    assert proposal is not None
    assert proposal.title == "Proposal title"


async def test_patch_proposal_invalid_date_range_returns_422() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        _,
        proposal_repo,
        _,
    ):
        # Stored begin is 2026-06-01; patching only the end to an earlier date
        # must be rejected against the effective (stored + incoming) range.
        await proposal_repo.add(_proposal())

        response = await client.patch(
            "/api/v1/proposals/prop-1",
            json={"endDate": "2026-05-01"},
        )
        proposal = await proposal_repo.get_by_id(ProposalId("prop-1"))

    assert response.status_code == 422
    assert response.json()["error"] == "INVALID_DATE_RANGE"
    assert proposal is not None
    assert proposal.end_date == date(2026, 6, 7)


async def test_patch_proposal_unknown_id_returns_404() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (client, _, _, _):
        response = await client.patch(
            "/api/v1/proposals/missing",
            json={"title": "x"},
        )

    assert response.status_code == 404
    assert response.json()["error"] == "PROPOSAL_NOT_FOUND"


async def test_approve_proposal_invalid_date_range_returns_422() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        _,
        proposal_repo,
        _,
    ):
        await proposal_repo.add(
            Proposal(
                id=ProposalId("prop-1"),
                reference_number=ReferenceNumber("VRP-20260601-0001"),
                title="Proposal title",
                collection_use_project_id=CollectionUseProjectId("proj-1"),
                intended_use=UseType.IN_SITU_VISIT,
                begin_date=date(2026, 6, 1),
                end_date=date(2026, 6, 7),
                status=ProposalStatus.PENDING,
                requested_by=PermissionId("permission-1"),
                submitted_at=datetime(2026, 6, 7, tzinfo=UTC),
            )
        )

        response = await client.post(
            "/api/v1/proposals/prop-1/approve",
            json={
                "title": "Approved project",
                "purpose": "Use the collection",
                "beginDate": "2026-06-07",
                "endDate": "2026-06-01",
            },
        )

    assert response.status_code == 422
    assert response.json()["error"] == "INVALID_DATE_RANGE"
    assert response.json()["message"] == "endDate must be after beginDate"


async def test_approve_public_proposal_sends_access_email_after_commit() -> None:
    resolved = ResolvedExternalRequester(
        actor=Actor(
            id=PermissionId("permission-external-1"),
            group=GroupName.EXTERNAL,
            email="pedro@example.test",
        ),
        temporary_password="Temp-Pw-123!",
    )
    requester_provisioner = RecordingRequesterProvisioner(resolved)
    access_email_sender = RecordingAccessEmailSender()

    async with client_with_repos(
        caller=_STAFF_CALLER,
        requester_provisioner=requester_provisioner,
        access_email_sender=access_email_sender,
    ) as (client, _, proposal_repo, _):
        await proposal_repo.add(
            Proposal(
                id=ProposalId("prop-1"),
                reference_number=ReferenceNumber("VRP-20260601-0001"),
                title="Proposal title",
                collection_use_project_id=None,
                intended_use=UseType.IN_SITU_VISIT,
                begin_date=date(2026, 6, 1),
                end_date=date(2026, 6, 7),
                status=ProposalStatus.PENDING,
                requested_by=None,
                requester_contact=RequesterContact(
                    name="Pedro Silva", email=EmailAddress("pedro@example.test")
                ),
                submitted_at=datetime(2026, 6, 7, tzinfo=UTC),
            )
        )

        response = await client.post(
            "/api/v1/proposals/prop-1/approve",
            json={
                "title": "Approved project",
                "purpose": "Use the collection",
                "beginDate": "2026-06-07",
                "endDate": "2026-06-30",
            },
        )

    assert response.status_code == 200
    assert response.json()["collectionUseProject"]["requestedBy"]["permissionId"] == (
        "permission-external-1"
    )
    # The credentials e-mail is only ever dispatched once the approval (and
    # the request that provisioned it) is committed — see approve_proposal.
    assert access_email_sender.calls == [
        (
            "pedro@example.test",
            "Pedro Silva",
            f"{settings.public_origin}/login",
            "Temp-Pw-123!",
        )
    ]


async def test_cancel_proposal_by_requester_without_project_returns_cancelled() -> None:
    async with client_with_repos() as (client, project_repo, proposal_repo, _):
        await proposal_repo.add(_proposal(status=ProposalStatus.SUBMITTED))

        response = await client.post(
            "/api/v1/proposals/prop-1/cancel",
            json={"reason": "Research trip cancelled"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["proposal"]["status"] == "CANCELLED"
    assert body["proposal"]["lastEvent"]["type"] == "CANCELLED"
    assert body["proposal"]["lastEvent"]["note"] == "Research trip cancelled"
    assert body["collectionUseProject"] is None
    assert proposal_repo.items["prop-1"].status == ProposalStatus.CANCELLED
    assert project_repo.items == {}


async def test_cancel_proposal_cascades_to_existing_project_any_status() -> None:
    async with client_with_repos() as (client, project_repo, proposal_repo, _):
        await proposal_repo.add(_proposal(status=ProposalStatus.APPROVED))
        await project_repo.add(_project(status=UseStatus.COMPLETED))

        response = await client.post(
            "/api/v1/proposals/prop-1/cancel",
            json={"reason": "No longer needed"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["proposal"]["status"] == "CANCELLED"
    assert body["collectionUseProject"]["status"] == "CANCELLED"
    assert proposal_repo.items["prop-1"].events[-1].type.value == "CANCELLED"
    assert project_repo.items["proj-1"].status == UseStatus.CANCELLED
    assert project_repo.items["proj-1"].result.value == "CANCELLED"
    assert project_repo.items["proj-1"].events[-1].type.value == "CANCELLED"


async def test_cancel_proposal_rejects_non_requester() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        _,
        proposal_repo,
        _,
    ):
        await proposal_repo.add(_proposal(status=ProposalStatus.PENDING))

        response = await client.post(
            "/api/v1/proposals/prop-1/cancel",
            json={"reason": "Trying to cancel"},
        )

    assert response.status_code == 403
    assert response.json()["error"] == "ACCESS_DENIED"
    assert proposal_repo.items["prop-1"].status == ProposalStatus.PENDING


async def test_cancel_proposal_rejects_rejected_status() -> None:
    async with client_with_repos() as (client, project_repo, proposal_repo, _):
        await proposal_repo.add(_proposal(status=ProposalStatus.REJECTED))
        await project_repo.add(_project(status=UseStatus.CREATED))

        response = await client.post(
            "/api/v1/proposals/prop-1/cancel",
            json={"reason": "No longer needed"},
        )

    assert response.status_code == 409
    assert response.json()["error"] == "INVALID_TRANSITION"
    assert response.json()["message"] == "Cannot cancel a rejected proposal"
    assert proposal_repo.items["prop-1"].status == ProposalStatus.REJECTED
    assert project_repo.items["proj-1"].status == UseStatus.CREATED
    assert project_repo.items["proj-1"].events == []


async def test_submit_document_empty_document_type_returns_422() -> None:
    async with client_with_repos() as (client, _, proposal_repo, _):
        await proposal_repo.add(
            Proposal(
                id=ProposalId("prop-1"),
                reference_number=ReferenceNumber("VRP-20260601-0001"),
                title="Proposal title",
                collection_use_project_id=CollectionUseProjectId("proj-1"),
                intended_use=UseType.IN_SITU_VISIT,
                begin_date=date(2026, 6, 1),
                end_date=date(2026, 6, 7),
                status=ProposalStatus.PENDING,
                requested_by=PermissionId("permission-1"),
                submitted_at=datetime(2026, 6, 7, tzinfo=UTC),
            )
        )

        response = await client.post(
            "/api/v1/proposals/prop-1/documents",
            files={"file": ("request.docx", b"docx", "application/vnd.ms-word")},
            data={"documentType": ""},
            headers={"X-Permission-Id": "permission-1"},
        )

    assert response.status_code == 422
    assert response.json()["message"] == "Validation failed"


def _pending_proposal() -> "Proposal":
    return Proposal(
        id=ProposalId("prop-1"),
        reference_number=ReferenceNumber("VRP-20260601-0001"),
        title="Proposal title",
        collection_use_project_id=CollectionUseProjectId("proj-1"),
        intended_use=UseType.IN_SITU_VISIT,
        begin_date=date(2026, 6, 1),
        end_date=date(2026, 6, 7),
        status=ProposalStatus.PENDING,
        requested_by=PermissionId("permission-1"),
        submitted_at=datetime(2026, 6, 7, tzinfo=UTC),
    )


async def test_submit_document_rejects_non_docx_content() -> None:
    async with client_with_repos() as (client, _, proposal_repo, _):
        await proposal_repo.add(_pending_proposal())
        response = await client.post(
            "/api/v1/proposals/prop-1/documents",
            files={"file": ("request.docx", b"not a real zip", "application/octet")},
            data={"documentType": "REQUEST_FORM"},
            headers={"X-Permission-Id": "permission-1"},
        )
    assert response.status_code == 415
    assert response.json()["error"] == "INVALID_FILE_FORMAT"


async def test_submit_document_accepts_valid_docx() -> None:
    async with client_with_repos() as (client, _, proposal_repo, _):
        await proposal_repo.add(_pending_proposal())
        response = await client.post(
            "/api/v1/proposals/prop-1/documents",
            files={
                "file": (
                    "request.docx",
                    _docx_bytes(),
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
            data={"documentType": "REQUEST_FORM"},
            headers={"X-Permission-Id": "permission-1"},
        )
    assert response.status_code == 201


async def test_download_document_returns_file_bytes() -> None:
    document = Document(
        id=DocumentId("doc-1"),
        type=DocumentType("RESEARCH_FORM"),
        file_name="research_form.docx",
        file_reference="stored.docx",
        submitted_at=datetime(2026, 6, 7, tzinfo=UTC),
        submitted_by=PermissionId("permission-1"),
    )
    async with client_with_repos() as (client, _, proposal_repo, _):
        file_storage = app.dependency_overrides[get_file_storage]()
        file_storage.files["stored.docx"] = b"docx bytes"
        await proposal_repo.add(_proposal(documents=[document]))

        response = await client.get(
            "/api/v1/proposals/prop-1/documents/doc-1",
            headers={"X-Permission-Id": "permission-1"},
        )

    assert response.status_code == 200
    assert response.content == b"docx bytes"
    assert response.headers["content-type"] == (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert response.headers["content-disposition"] == (
        'attachment; filename="research_form.docx"'
    )


async def test_download_document_unknown_document_returns_404() -> None:
    async with client_with_repos() as (client, _, proposal_repo, _):
        await proposal_repo.add(_proposal())

        response = await client.get(
            "/api/v1/proposals/prop-1/documents/missing-doc",
            headers={"X-Permission-Id": "permission-1"},
        )

    assert response.status_code == 404
    assert response.json()["error"] == "NOT_FOUND"
    assert response.json()["message"] == "Document not found for this proposal"


async def test_download_document_rejects_non_owner() -> None:
    document = Document(
        id=DocumentId("doc-1"),
        type=DocumentType("RESEARCH_FORM"),
        file_name="research_form.docx",
        file_reference="stored.docx",
        submitted_at=datetime(2026, 6, 7, tzinfo=UTC),
        submitted_by=PermissionId("permission-other"),
    )
    async with client_with_repos() as (client, _, proposal_repo, _):
        await proposal_repo.add(
            _proposal(
                requested_by=PermissionId("permission-other"),
                documents=[document],
            )
        )

        response = await client.get(
            "/api/v1/proposals/prop-1/documents/doc-1",
            headers={"X-Permission-Id": "permission-1"},
        )

    assert response.status_code == 403
    assert response.json()["error"] == "ACCESS_DENIED"


async def test_log_entry_attachment_invalid_media_type_returns_422() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        project_repo,
        proposal_repo,
        _,
    ):
        project_id = CollectionUseProjectId("project-1")
        await project_repo.add(
            CollectionUseProject(
                id=project_id,
                reference_number=ReferenceNumber("CUP-ABCDEFG1"),
                title="Project",
                purpose="Use collection",
                intended_use=UseType.IN_SITU_VISIT,
                status=UseStatus.CREATED,
                begin_date=date(2026, 6, 1),
                end_date=date(2026, 6, 7),
                requested_by=PermissionId("permission-1"),
            )
        )
        await proposal_repo.add(
            Proposal(
                id=ProposalId("prop-1"),
                reference_number=ReferenceNumber("VRP-20260601-0001"),
                title="Proposal title",
                collection_use_project_id=project_id,
                intended_use=UseType.IN_SITU_VISIT,
                begin_date=date(2026, 6, 1),
                end_date=date(2026, 6, 7),
                status=ProposalStatus.APPROVED,
                requested_by=PermissionId("permission-1"),
                submitted_at=datetime(2026, 6, 7, tzinfo=UTC),
            )
        )
        log_repo = app.dependency_overrides[get_access_log_repo]()
        await log_repo.add(
            ObjectAccessLog(
                id=ObjectAccessLogId("log-1"),
                reference_number=ReferenceNumber("OAL-ABCDEFG1"),
                collection_use_project_id=project_id,
            )
        )
        await log_repo.save_entry(
            ObjectLogEntry(
                id=ObjectLogEntryId("entry-1"),
                object_access_log_id=ObjectAccessLogId("log-1"),
                collection_use_object_id=CollectionUseObjectId("cuo-1"),
                number_of_objects=1,
                added_at=datetime(2026, 6, 7, tzinfo=UTC),
                added_by=PermissionId("permission-staff"),
            )
        )

        response = await client.post(
            "/api/v1/collection-use-projects/project-1/log-entries/entry-1/attachments",
            files={"file": ("photo.jpg", b"jpeg", "image/jpeg")},
            data={"mediaType": "NOT_A_MEDIA_TYPE"},
        )

    assert response.status_code == 422
    assert response.json()["error"] == "VALIDATION_ERROR"


async def test_log_entry_attachment_persists_optional_note() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        project_repo,
        proposal_repo,
        _,
    ):
        await project_repo.add(
            _project(
                "project-1",
                status=UseStatus.IN_PROGRESS,
                objects=[_collection_use_object()],
            )
        )
        created = await client.post(
            "/api/v1/collection-use-projects/project-1/log-entries",
            json={"collectionUseObjectId": "cuo-1", "numberOfObjects": 1},
            headers={"X-Permission-Id": "permission-staff"},
        )
        entry_id = created.json()["id"]

        with_note = await client.post(
            f"/api/v1/collection-use-projects/project-1/log-entries/{entry_id}/attachments",
            files={"file": ("photo.jpg", b"jpeg", "image/jpeg")},
            data={"mediaType": "IMAGE", "note": "Front view"},
            headers={"X-Permission-Id": "permission-staff"},
        )
        without_note = await client.post(
            f"/api/v1/collection-use-projects/project-1/log-entries/{entry_id}/attachments",
            files={"file": ("doc.pdf", b"pdf", "application/pdf")},
            data={"mediaType": "DOCUMENT"},
            headers={"X-Permission-Id": "permission-staff"},
        )
        listing = await client.get(
            "/api/v1/collection-use-projects/project-1/log-entries",
            headers={"X-Permission-Id": "permission-staff"},
        )

    assert with_note.status_code == 201
    assert with_note.json()["note"] == "Front view"
    assert without_note.status_code == 201
    assert without_note.json()["note"] is None
    # The note survives the round-trip through the listing endpoint.
    notes = {a["note"] for a in listing.json()["content"][0]["attachments"]}
    assert notes == {"Front view", None}


async def test_download_log_entry_attachment_returns_file() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        project_repo,
        proposal_repo,
        _,
    ):
        await project_repo.add(
            _project(
                "project-1",
                status=UseStatus.IN_PROGRESS,
                objects=[_collection_use_object()],
            )
        )
        created = await client.post(
            "/api/v1/collection-use-projects/project-1/log-entries",
            json={"collectionUseObjectId": "cuo-1", "numberOfObjects": 1},
            headers={"X-Permission-Id": "permission-staff"},
        )
        entry_id = created.json()["id"]
        uploaded = await client.post(
            f"/api/v1/collection-use-projects/project-1/log-entries/{entry_id}/attachments",
            files={"file": ("report.pdf", b"%PDF-1.4 bytes", "application/pdf")},
            data={"mediaType": "DOCUMENT"},
            headers={"X-Permission-Id": "permission-staff"},
        )
        file_reference = uploaded.json()["fileReference"]

        download = await client.get(
            f"/api/v1/collection-use-projects/project-1/log-entries/{entry_id}/attachments/{file_reference}",
            headers={"X-Permission-Id": "permission-staff"},
        )

    assert download.status_code == 200
    assert download.content == b"%PDF-1.4 bytes"
    assert download.headers["content-type"].startswith("application/pdf")
    assert "report.pdf" in download.headers["content-disposition"]


async def test_download_log_entry_attachment_unknown_reference_returns_404() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        project_repo,
        proposal_repo,
        _,
    ):
        await project_repo.add(
            _project(
                "project-1",
                status=UseStatus.IN_PROGRESS,
                objects=[_collection_use_object()],
            )
        )
        created = await client.post(
            "/api/v1/collection-use-projects/project-1/log-entries",
            json={"collectionUseObjectId": "cuo-1", "numberOfObjects": 1},
            headers={"X-Permission-Id": "permission-staff"},
        )
        entry_id = created.json()["id"]

        response = await client.get(
            f"/api/v1/collection-use-projects/project-1/log-entries/{entry_id}/attachments/does-not-exist",
            headers={"X-Permission-Id": "permission-staff"},
        )

    assert response.status_code == 404
    assert response.json()["error"] == "ATTACHMENT_NOT_FOUND"


async def test_download_occurrence_entry_attachment_returns_file() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        project_repo,
        proposal_repo,
        _,
    ):
        await project_repo.add(
            _project(
                "project-1",
                status=UseStatus.IN_PROGRESS,
                objects=[_collection_use_object()],
            )
        )
        created = await client.post(
            "/api/v1/collection-use-projects/project-1/occurrence-entries",
            json={
                "collectionUseObjectId": "cuo-1",
                "numberOfObjects": 1,
                "occurrenceDate": "2026-06-03T11:30:00Z",
                "location": "Lab",
                "detailedDescription": "desc",
            },
            headers={"X-Permission-Id": "permission-staff"},
        )
        entry_id = created.json()["id"]
        uploaded = await client.post(
            f"/api/v1/collection-use-projects/project-1/occurrence-entries/{entry_id}/attachments",
            files={"file": ("photo.jpg", b"jpegbytes", "image/jpeg")},
            data={"mediaType": "IMAGE"},
            headers={"X-Permission-Id": "permission-staff"},
        )
        file_reference = uploaded.json()["fileReference"]

        download = await client.get(
            f"/api/v1/collection-use-projects/project-1/occurrence-entries/{entry_id}/attachments/{file_reference}",
            headers={"X-Permission-Id": "permission-staff"},
        )

    assert download.status_code == 200
    assert download.content == b"jpegbytes"
    assert download.headers["content-type"].startswith("image/jpeg")
    assert "photo.jpg" in download.headers["content-disposition"]


async def test_add_log_entry_returns_201_with_access_log_created() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        project_repo,
        proposal_repo,
        _,
    ):
        await project_repo.add(
            _project(
                "project-1",
                status=UseStatus.IN_PROGRESS,
                objects=[_collection_use_object()],
            )
        )

        response = await client.post(
            "/api/v1/collection-use-projects/project-1/log-entries",
            json={
                "collectionUseObjectId": "cuo-1",
                "numberOfObjects": 2,
                "observations": "Handled with gloves",
            },
            headers={"X-Permission-Id": "permission-staff"},
        )

        assert response.status_code == 201
        body = response.json()
        assert body["collectionUseObjectId"] == "cuo-1"
        assert body["numberOfObjects"] == 2
        assert body["observations"] == "Handled with gloves"
        assert body["attachments"] == []

        listing = await client.get(
            "/api/v1/collection-use-projects/project-1/log-entries",
            headers={"X-Permission-Id": "permission-staff"},
        )

    assert listing.status_code == 200
    listing_body = listing.json()
    assert listing_body["accessLog"]["referenceNumber"].startswith("OAL-")
    assert listing_body["accessLog"]["dateConclusion"] is None
    assert listing_body["accessLog"]["curator"] is None
    assert listing_body["totalElements"] == 1
    assert listing_body["content"][0]["numberOfObjects"] == 2


async def test_edit_log_entry_updates_editable_fields() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        project_repo,
        proposal_repo,
        _,
    ):
        await project_repo.add(
            _project(
                "project-1",
                status=UseStatus.IN_PROGRESS,
                objects=[_collection_use_object()],
            )
        )
        created = await client.post(
            "/api/v1/collection-use-projects/project-1/log-entries",
            json={
                "collectionUseObjectId": "cuo-1",
                "numberOfObjects": 2,
                "observations": "original",
            },
            headers={"X-Permission-Id": "permission-staff"},
        )
        entry_id = created.json()["id"]

        edited = await client.patch(
            f"/api/v1/collection-use-projects/project-1/log-entries/{entry_id}",
            json={
                "addedAt": "2025-06-03T14:00:00",
                "numberOfObjects": 5,
                "observations": "corrected",
            },
            headers={"X-Permission-Id": "permission-staff"},
        )

    assert edited.status_code == 200
    body = edited.json()
    assert body["id"] == entry_id
    assert body["numberOfObjects"] == 5
    assert body["observations"] == "corrected"
    assert body["addedAt"] == "2025-06-03T14:00:00"
    # Immutable fields are preserved.
    assert body["collectionUseObjectId"] == "cuo-1"
    assert body["addedBy"]["permissionId"] == "permission-staff"


async def test_edit_log_entry_is_partial_and_clears_observations() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        project_repo,
        proposal_repo,
        _,
    ):
        await project_repo.add(
            _project(
                "project-1",
                status=UseStatus.IN_PROGRESS,
                objects=[_collection_use_object()],
            )
        )
        created = await client.post(
            "/api/v1/collection-use-projects/project-1/log-entries",
            json={
                "collectionUseObjectId": "cuo-1",
                "numberOfObjects": 2,
                "observations": "original",
            },
            headers={"X-Permission-Id": "permission-staff"},
        )
        entry_id = created.json()["id"]

        # Omitting numberOfObjects leaves it untouched; null clears observations.
        edited = await client.patch(
            f"/api/v1/collection-use-projects/project-1/log-entries/{entry_id}",
            json={"observations": None},
            headers={"X-Permission-Id": "permission-staff"},
        )

    assert edited.status_code == 200
    body = edited.json()
    assert body["numberOfObjects"] == 2
    assert body["observations"] is None


async def test_edit_log_entry_unknown_entry_returns_404() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        project_repo,
        _,
        _,
    ):
        await project_repo.add(_project("project-1", status=UseStatus.IN_PROGRESS))

        response = await client.patch(
            "/api/v1/collection-use-projects/project-1/log-entries/missing",
            json={"numberOfObjects": 3},
            headers={"X-Permission-Id": "permission-staff"},
        )

    assert response.status_code == 404
    assert response.json()["error"] == "ENTRY_NOT_FOUND"


async def test_log_entry_links_to_requested_object_over_http() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        project_repo,
        proposal_repo,
        _,
    ):
        await project_repo.add(
            _project(
                "project-1",
                status=UseStatus.IN_PROGRESS,
                objects=[_collection_use_object()],
            )
        )

        ok = await client.post(
            "/api/v1/collection-use-projects/project-1/log-entries",
            json={
                "numberOfObjects": 1,
                "collectionUseObjectId": "cuo-1",
            },
            headers={"X-Permission-Id": "permission-staff"},
        )
        unknown = await client.post(
            "/api/v1/collection-use-projects/project-1/log-entries",
            json={
                "numberOfObjects": 1,
                "collectionUseObjectId": "does-not-exist",
            },
            headers={"X-Permission-Id": "permission-staff"},
        )

    assert ok.status_code == 201
    assert ok.json()["collectionUseObjectId"] == "cuo-1"
    assert unknown.status_code == 422
    assert unknown.json()["error"] == "VALIDATION_ERROR"


async def test_get_object_access_log_returns_404_without_entries() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        project_repo,
        _,
        _,
    ):
        await project_repo.add(_project("project-1", status=UseStatus.IN_PROGRESS))

        response = await client.get(
            "/api/v1/collection-use-projects/project-1/object-access-log",
            headers={"X-Permission-Id": "permission-staff"},
        )

    assert response.status_code == 404
    assert response.json()["error"] == "OBJECT_ACCESS_LOG_NOT_FOUND"


async def test_add_occurrence_entry_returns_201_with_occurrence_log_created() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        project_repo,
        proposal_repo,
        _,
    ):
        await project_repo.add(
            _project(
                "project-1",
                status=UseStatus.IN_PROGRESS,
                objects=[_collection_use_object()],
            )
        )

        response = await client.post(
            "/api/v1/collection-use-projects/project-1/occurrence-entries",
            json={
                "collectionUseObjectId": "cuo-1",
                "numberOfObjects": 2,
                "occurrenceDate": "2026-06-03T11:30:00Z",
                "location": "Conservation lab",
                "detailedDescription": "Minor abrasion observed",
                "testimonial": "Reported by the conservator",
            },
            headers={"X-Permission-Id": "permission-staff"},
        )

        assert response.status_code == 201
        body = response.json()
        assert body["collectionUseObjectId"] == "cuo-1"
        assert body["numberOfObjects"] == 2
        assert body["location"] == "Conservation lab"
        assert body["detailedDescription"] == "Minor abrasion observed"
        assert body["testimonial"] == "Reported by the conservator"
        assert body["attachments"] == []

        listing = await client.get(
            "/api/v1/collection-use-projects/project-1/occurrence-entries",
            headers={"X-Permission-Id": "permission-staff"},
        )

    assert listing.status_code == 200
    listing_body = listing.json()
    assert listing_body["occurrenceLog"]["referenceNumber"].startswith("OOL-")
    assert listing_body["occurrenceLog"]["dateConclusion"] is None
    assert listing_body["occurrenceLog"]["curator"] is None
    assert listing_body["totalElements"] == 1
    assert listing_body["content"][0]["numberOfObjects"] == 2


def _add_occurrence_entry_payload() -> dict[str, object]:
    return {
        "collectionUseObjectId": "cuo-1",
        "numberOfObjects": 2,
        "occurrenceDate": "2026-06-03T11:30:00Z",
        "location": "Conservation lab",
        "detailedDescription": "Minor abrasion observed",
        "testimonial": "Reported by the conservator",
    }


async def test_edit_occurrence_entry_updates_editable_fields() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        project_repo,
        proposal_repo,
        _,
    ):
        await project_repo.add(
            _project(
                "project-1",
                status=UseStatus.IN_PROGRESS,
                objects=[_collection_use_object()],
            )
        )
        created = await client.post(
            "/api/v1/collection-use-projects/project-1/occurrence-entries",
            json=_add_occurrence_entry_payload(),
            headers={"X-Permission-Id": "permission-staff"},
        )
        entry_id = created.json()["id"]

        edited = await client.patch(
            f"/api/v1/collection-use-projects/project-1/occurrence-entries/{entry_id}",
            json={
                "numberOfObjects": 5,
                "occurrenceDate": "2026-06-04T09:00:00Z",
                "location": "Main gallery",
                "detailedDescription": "Re-examined under raking light",
                "testimonial": "Confirmed by the curator",
            },
            headers={"X-Permission-Id": "permission-staff"},
        )

    assert edited.status_code == 200
    body = edited.json()
    assert body["id"] == entry_id
    assert body["numberOfObjects"] == 5
    assert body["occurrenceDate"] == "2026-06-04T09:00:00Z"
    assert body["location"] == "Main gallery"
    assert body["detailedDescription"] == "Re-examined under raking light"
    assert body["testimonial"] == "Confirmed by the curator"
    # Immutable fields are preserved.
    assert body["collectionUseObjectId"] == "cuo-1"
    assert body["reportedBy"]["permissionId"] == "permission-staff"


async def test_edit_occurrence_entry_is_partial_and_clears_testimonial() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        project_repo,
        proposal_repo,
        _,
    ):
        await project_repo.add(
            _project(
                "project-1",
                status=UseStatus.IN_PROGRESS,
                objects=[_collection_use_object()],
            )
        )
        created = await client.post(
            "/api/v1/collection-use-projects/project-1/occurrence-entries",
            json=_add_occurrence_entry_payload(),
            headers={"X-Permission-Id": "permission-staff"},
        )
        entry_id = created.json()["id"]

        # Omitting other fields leaves them untouched; null clears testimonial.
        edited = await client.patch(
            f"/api/v1/collection-use-projects/project-1/occurrence-entries/{entry_id}",
            json={"testimonial": None},
            headers={"X-Permission-Id": "permission-staff"},
        )

    assert edited.status_code == 200
    body = edited.json()
    assert body["numberOfObjects"] == 2
    assert body["location"] == "Conservation lab"
    assert body["detailedDescription"] == "Minor abrasion observed"
    assert body["testimonial"] is None


async def test_edit_occurrence_entry_unknown_entry_returns_404() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        project_repo,
        _,
        _,
    ):
        await project_repo.add(_project("project-1", status=UseStatus.IN_PROGRESS))

        response = await client.patch(
            "/api/v1/collection-use-projects/project-1/occurrence-entries/missing",
            json={"numberOfObjects": 3},
            headers={"X-Permission-Id": "permission-staff"},
        )

    assert response.status_code == 404
    assert response.json()["error"] == "ENTRY_NOT_FOUND"


async def test_get_object_occurrence_log_returns_404_without_entries() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        project_repo,
        _,
        _,
    ):
        await project_repo.add(_project("project-1", status=UseStatus.IN_PROGRESS))

        response = await client.get(
            "/api/v1/collection-use-projects/project-1/object-occurrence-log",
            headers={"X-Permission-Id": "permission-staff"},
        )

    assert response.status_code == 404
    assert response.json()["error"] == "OBJECT_OCCURRENCE_LOG_NOT_FOUND"


# ── Publication log ──────────────────────────────────────────────────────────


def _project_proposal(
    requested_by: str = "permission-1",
    assigned_to: str | None = None,
) -> Proposal:
    """A proposal linked to project-1 (for project-access + curator snapshot)."""
    proposal = _proposal("prop-pub", requested_by=PermissionId(requested_by))
    proposal.collection_use_project_id = CollectionUseProjectId("project-1")
    if assigned_to is not None:
        proposal.assigned_to = PermissionId(assigned_to)
    return proposal


async def test_add_publication_entry_in_progress_external_creates_log() -> None:
    async with client_with_repos(caller=_CALLER) as (
        client,
        project_repo,
        proposal_repo,
        _,
    ):
        await project_repo.add(_project("project-1", status=UseStatus.IN_PROGRESS))
        await proposal_repo.add(_project_proposal(assigned_to="permission-staff"))

        response = await client.post(
            "/api/v1/collection-use-projects/project-1/publication-entries",
            json={"note": "Published an article in the museum journal"},
            headers={"X-Permission-Id": "permission-1"},
        )

        assert response.status_code == 201
        body = response.json()
        assert body["note"] == "Published an article in the museum journal"
        assert body["addedBy"]["permissionId"] == "permission-1"
        assert body["attachments"] == []

        listing = await client.get(
            "/api/v1/collection-use-projects/project-1/publication-entries",
            headers={"X-Permission-Id": "permission-1"},
        )

    assert listing.status_code == 200
    listing_body = listing.json()
    assert listing_body["publicationLog"]["referenceNumber"].startswith("PUB-")
    # curator is the informational snapshot of the proposal's assignee
    assert listing_body["publicationLog"]["curator"]["permissionId"] == (
        "permission-staff"
    )
    assert listing_body["totalElements"] == 1
    assert listing_body["content"][0]["note"].startswith("Published")


async def test_add_publication_entry_staff_while_in_progress_rejected() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        project_repo,
        _,
        _,
    ):
        await project_repo.add(_project("project-1", status=UseStatus.IN_PROGRESS))

        response = await client.post(
            "/api/v1/collection-use-projects/project-1/publication-entries",
            json={"note": "Staff cannot write while in progress"},
            headers={"X-Permission-Id": "permission-staff"},
        )

    assert response.status_code == 403
    assert response.json()["error"] == "ACCESS_DENIED"


async def test_add_publication_entry_staff_once_completed_ok() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        project_repo,
        _,
        _,
    ):
        await project_repo.add(_project("project-1", status=UseStatus.COMPLETED))

        response = await client.post(
            "/api/v1/collection-use-projects/project-1/publication-entries",
            json={"note": "Final exhibition catalogue entry"},
            headers={"X-Permission-Id": "permission-staff"},
        )

    assert response.status_code == 201
    assert response.json()["note"] == "Final exhibition catalogue entry"


async def test_add_publication_entry_external_once_completed_rejected() -> None:
    async with client_with_repos(caller=_CALLER) as (
        client,
        project_repo,
        proposal_repo,
        _,
    ):
        await project_repo.add(_project("project-1", status=UseStatus.COMPLETED))
        await proposal_repo.add(_project_proposal())

        response = await client.post(
            "/api/v1/collection-use-projects/project-1/publication-entries",
            json={"note": "External cannot write once completed"},
            headers={"X-Permission-Id": "permission-1"},
        )

    assert response.status_code == 403
    assert response.json()["error"] == "ACCESS_DENIED"


async def test_add_publication_entry_in_created_status_rejected() -> None:
    async with client_with_repos(caller=_CALLER) as (
        client,
        project_repo,
        proposal_repo,
        _,
    ):
        await project_repo.add(_project("project-1", status=UseStatus.CREATED))
        await proposal_repo.add(_project_proposal())

        response = await client.post(
            "/api/v1/collection-use-projects/project-1/publication-entries",
            json={"note": "No writes before the project starts"},
            headers={"X-Permission-Id": "permission-1"},
        )

    assert response.status_code == 409
    assert response.json()["error"] == "INVALID_TRANSITION"


async def test_edit_publication_entry_updates_note() -> None:
    async with client_with_repos(caller=_CALLER) as (
        client,
        project_repo,
        proposal_repo,
        _,
    ):
        await project_repo.add(_project("project-1", status=UseStatus.IN_PROGRESS))
        await proposal_repo.add(_project_proposal())
        created = await client.post(
            "/api/v1/collection-use-projects/project-1/publication-entries",
            json={"note": "original"},
            headers={"X-Permission-Id": "permission-1"},
        )
        entry_id = created.json()["id"]

        edited = await client.patch(
            f"/api/v1/collection-use-projects/project-1/publication-entries/{entry_id}",
            json={"note": "corrected"},
            headers={"X-Permission-Id": "permission-1"},
        )

    assert edited.status_code == 200
    body = edited.json()
    assert body["id"] == entry_id
    assert body["note"] == "corrected"
    assert body["addedBy"]["permissionId"] == "permission-1"


async def test_publication_entry_attachment_upload_and_download() -> None:
    async with client_with_repos(caller=_CALLER) as (
        client,
        project_repo,
        proposal_repo,
        _,
    ):
        await project_repo.add(_project("project-1", status=UseStatus.IN_PROGRESS))
        await proposal_repo.add(_project_proposal())
        created = await client.post(
            "/api/v1/collection-use-projects/project-1/publication-entries",
            json={"note": "with attachment"},
            headers={"X-Permission-Id": "permission-1"},
        )
        entry_id = created.json()["id"]
        uploaded = await client.post(
            f"/api/v1/collection-use-projects/project-1/publication-entries/{entry_id}/attachments",
            files={"file": ("paper.pdf", b"%PDF-1.4 paper", "application/pdf")},
            data={"mediaType": "DOCUMENT", "note": "the publication itself"},
            headers={"X-Permission-Id": "permission-1"},
        )
        assert uploaded.status_code == 201
        file_reference = uploaded.json()["fileReference"]

        download = await client.get(
            f"/api/v1/collection-use-projects/project-1/publication-entries/{entry_id}/attachments/{file_reference}",
            headers={"X-Permission-Id": "permission-1"},
        )

    assert download.status_code == 200
    assert download.content == b"%PDF-1.4 paper"
    assert "paper.pdf" in download.headers["content-disposition"]


async def test_get_publication_log_returns_404_without_entries() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        project_repo,
        _,
        _,
    ):
        await project_repo.add(_project("project-1", status=UseStatus.IN_PROGRESS))

        response = await client.get(
            "/api/v1/collection-use-projects/project-1/publication-log",
            headers={"X-Permission-Id": "permission-staff"},
        )

    assert response.status_code == 404
    assert response.json()["error"] == "PUBLICATION_LOG_NOT_FOUND"
