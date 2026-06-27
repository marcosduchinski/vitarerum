"""Golden contract tests (HEXAGONAL_UP.md Step 0).

Characterization tests that freeze the JSON *shape* (full key-path set) and the
error bodies of the contract-sensitive endpoints. They must stay green through
every refactor step; a failure here means an API contract changed.
"""

from app.identity.domain.enums import GroupName
from app.use_of_collections.domain.enums import UseStatus
from test.use_of_collections.test_api import (
    _CALLER,
    _STAFF_CALLER,
    _collection_use_object,
    _permission_record,
    _project,
    _project_proposal,
    _proposal,
    client_with_repos,
)

_REQUESTER_RECORDS = {
    "permission-1": _permission_record("permission-1", GroupName.EXTERNAL)
}

_PERMISSION_DETAIL = {"permissionId", "user.id", "user.name", "user.email", "group"}


def _paths(value: object, prefix: str = "") -> set[str]:
    """Flatten a JSON body into its full set of key paths ([] marks list items)."""
    if isinstance(value, dict):
        if not value:
            return {prefix.rstrip(".") + ".{}"}
        out: set[str] = set()
        for key, item in value.items():
            out |= _paths(item, f"{prefix}{key}.")
        return out
    if isinstance(value, list):
        if not value:
            return {prefix.rstrip(".") + ".[]"}
        out = set()
        for item in value:
            out |= _paths(item, f"{prefix.rstrip('.')}[]" + ".")
        return out
    return {prefix.rstrip(".")}


def _nested(base: str, fields: set[str]) -> set[str]:
    return {f"{base}.{field}" for field in fields}


async def test_golden_submit_proposal_response_shape() -> None:
    async with client_with_repos() as (client, _, _, _):
        response = await client.post(
            "/api/v1/proposals",
            json={
                "title": "Collection study",
                "intendedUse": {"useType": "IN_SITU_VISIT", "description": "study"},
                "purpose": "To study the collection",
                "beginDate": "2026-06-01",
                "endDate": "2026-06-07",
            },
        )

    assert response.status_code == 201
    body = response.json()
    assert _paths(body) == (
        {
            "conversationId",
            "proposal.id",
            "proposal.referenceNumber",
            "proposal.title",
            "proposal.status",
            "proposal.intendedUse.useType",
            "proposal.intendedUse.description",
            "proposal.beginDate",
            "proposal.endDate",
            "proposal.assignedTo",
            "proposal.submittedAt",
        }
        | _nested("proposal.requestedBy", _PERMISSION_DETAIL)
    )
    assert body["proposal"]["referenceNumber"].startswith("VRP-")
    assert body["proposal"]["status"] == "SUBMITTED"


async def test_golden_proposal_detail_response_shape() -> None:
    async with client_with_repos(
        caller=_STAFF_CALLER, permission_records=_REQUESTER_RECORDS
    ) as (
        client,
        project_repo,
        proposal_repo,
        _,
    ):
        await proposal_repo.add(_proposal())
        await project_repo.add(_project())

        response = await client.get("/api/v1/proposals/prop-1")

    assert response.status_code == 200
    assert _paths(response.json()) == (
        {
            "id",
            "referenceNumber",
            "title",
            "status",
            "intendedUse.useType",
            "intendedUse.description",
            "beginDate",
            "endDate",
            "assignedTo",
            "collectionUseProject.id",
            "collectionUseProject.referenceNumber",
            "collectionUseProject.title",
            "collectionUseProject.status",
            "conversationId",
            "documents.[]",
            "requestedDocuments.[]",
            "requestedObjects.[]",
            "submittedAt",
        }
        | _nested("requestedBy", _PERMISSION_DETAIL)
        | _nested("collectionUseProject.requestedBy", _PERMISSION_DETAIL)
    )


async def test_golden_paginated_proposals_envelope_shape() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        project_repo,
        proposal_repo,
        _,
    ):
        await proposal_repo.add(_proposal())
        await project_repo.add(_project())

        response = await client.get("/api/v1/proposals")

    assert response.status_code == 200
    assert _paths(response.json()) == (
        {
            "page",
            "size",
            "totalElements",
            "totalPages",
            "content[].id",
            "content[].referenceNumber",
            "content[].title",
            "content[].status",
            "content[].intendedUse.useType",
            "content[].intendedUse.description",
            "content[].beginDate",
            "content[].endDate",
            "content[].assignedTo",
            "content[].submittedAt",
        }
        | _nested("content[].requestedBy", _PERMISSION_DETAIL)
    )


async def test_golden_project_detail_and_list_shapes() -> None:
    async with client_with_repos(
        caller=_STAFF_CALLER, permission_records=_REQUESTER_RECORDS
    ) as (
        client,
        project_repo,
        proposal_repo,
        _,
    ):
        await proposal_repo.add(_proposal())
        await project_repo.add(_project(objects=[_collection_use_object()]))

        detail = await client.get("/api/v1/collection-use-projects/proj-1")
        listing = await client.get("/api/v1/collection-use-projects")

    assert detail.status_code == 200
    proposal_summary = {
        "id",
        "referenceNumber",
        "title",
        "status",
        "beginDate",
        "endDate",
        "submittedAt",
        "assignedTo",
    }
    assert _paths(detail.json()) == (
        {
            "id",
            "referenceNumber",
            "title",
            "purpose",
            "note",
            "intendedUse.useType",
            "intendedUse.description",
            "status",
            "result",
            "beginDate",
            "endDate",
            "authorisedBy",
            "authorisedAt",
            "objects[].id",
            "objects[].inventoryNumber",
            "objects[].displayTitle",
            "objects[].objectName",
            "objects[].briefDescriptionSnapshot",
            "objects[].category",
            "objects[].description",
        }
        | {f"proposal.{f}" for f in proposal_summary}
        | _nested("requestedBy", _PERMISSION_DETAIL)
    )

    assert listing.status_code == 200
    assert _paths(listing.json()) == (
        {
            "page",
            "size",
            "totalElements",
            "totalPages",
            "content[].id",
            "content[].referenceNumber",
            "content[].title",
            "content[].purpose",
            "content[].note",
            "content[].intendedUse.useType",
            "content[].intendedUse.description",
            "content[].status",
            "content[].result",
            "content[].beginDate",
            "content[].endDate",
        }
        | {f"content[].proposal.{f}" for f in proposal_summary}
        | _nested("content[].requestedBy", _PERMISSION_DETAIL)
    )


async def test_golden_project_events_envelope_shape() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        project_repo,
        proposal_repo,
        _,
    ):
        from datetime import UTC, datetime

        from app.use_of_collections.domain.models import PermissionId

        project = _project(status=UseStatus.CREATED)
        project.record_requested(
            occurred_at=datetime(2026, 6, 1, tzinfo=UTC),
            triggered_by=PermissionId("permission-1"),
            note="Submitted",
        )
        await proposal_repo.add(_proposal())
        await project_repo.add(project)

        response = await client.get("/api/v1/collection-use-projects/proj-1/events")

    assert response.status_code == 200
    assert _paths(response.json()) == (
        {
            "projectId",
            "page",
            "size",
            "totalElements",
            "totalPages",
            "content[].occurredAt",
            "content[].type",
            "content[].note",
        }
        | _nested("content[].triggeredBy", _PERMISSION_DETAIL)
    )


async def test_golden_log_entries_shapes() -> None:
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
                "observations": "obs",
            },
        )
        listing = await client.get(
            "/api/v1/collection-use-projects/project-1/log-entries"
        )
        header = await client.get(
            "/api/v1/collection-use-projects/project-1/object-access-log"
        )

    entry_shape = {
        "id",
        "numberOfObjects",
        "addedAt",
        "observations",
        "collectionUseObjectId",
        "attachments.[]",
    }
    assert created.status_code == 201
    assert _paths(created.json()) == entry_shape | _nested(
        "addedBy", _PERMISSION_DETAIL
    )

    log_header_shape = {
        "id",
        "referenceNumber",
        "projectId",
        "dateConclusion",
        "curator",
    }
    assert listing.status_code == 200
    assert _paths(listing.json()) == (
        {"projectId", "page", "size", "totalElements", "totalPages"}
        | {f"accessLog.{f}" for f in log_header_shape if f != "projectId"}
        | {"accessLog.projectId"}
        | {f"content[].{p}" for p in entry_shape if p != "attachments.[]"}
        | {"content[].attachments.[]"}
        | _nested("content[].addedBy", _PERMISSION_DETAIL)
    )

    assert header.status_code == 200
    assert _paths(header.json()) == log_header_shape
    assert header.json()["referenceNumber"].startswith("OAL-")


async def test_golden_occurrence_entries_shapes() -> None:
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
                "testimonial": "test",
            },
        )
        listing = await client.get(
            "/api/v1/collection-use-projects/project-1/occurrence-entries"
        )

    entry_shape = {
        "id",
        "numberOfObjects",
        "occurrenceDate",
        "location",
        "detailedDescription",
        "testimonial",
        "collectionUseObjectId",
        "attachments.[]",
    }
    assert created.status_code == 201
    assert _paths(created.json()) == entry_shape | _nested(
        "reportedBy", _PERMISSION_DETAIL
    )

    assert listing.status_code == 200
    assert _paths(listing.json()) == (
        {"projectId", "page", "size", "totalElements", "totalPages"}
        | {
            "occurrenceLog.id",
            "occurrenceLog.referenceNumber",
            "occurrenceLog.projectId",
            "occurrenceLog.dateConclusion",
            "occurrenceLog.curator",
        }
        | {f"content[].{p}" for p in entry_shape if p != "attachments.[]"}
        | {"content[].attachments.[]"}
        | _nested("content[].reportedBy", _PERMISSION_DETAIL)
    )
    assert listing.json()["occurrenceLog"]["referenceNumber"].startswith("OOL-")


async def test_golden_publication_entries_shapes() -> None:
    async with client_with_repos(caller=_CALLER) as (
        client,
        project_repo,
        proposal_repo,
        _,
    ):
        await project_repo.add(_project("project-1", status=UseStatus.IN_PROGRESS))
        # No proposal assignee → curator stays null, freezing the leaf shape.
        await proposal_repo.add(_project_proposal())

        created = await client.post(
            "/api/v1/collection-use-projects/project-1/publication-entries",
            json={"note": "Published an article"},
        )
        listing = await client.get(
            "/api/v1/collection-use-projects/project-1/publication-entries"
        )
        header = await client.get(
            "/api/v1/collection-use-projects/project-1/publication-log"
        )

    entry_shape = {
        "id",
        "addedAt",
        "note",
        "attachments.[]",
    }
    assert created.status_code == 201
    assert _paths(created.json()) == entry_shape | _nested(
        "addedBy", _PERMISSION_DETAIL
    )

    log_header_shape = {"id", "referenceNumber", "projectId", "curator"}
    assert listing.status_code == 200
    assert _paths(listing.json()) == (
        {"projectId", "page", "size", "totalElements", "totalPages"}
        | {f"publicationLog.{f}" for f in log_header_shape}
        | {f"content[].{p}" for p in entry_shape if p != "attachments.[]"}
        | {"content[].attachments.[]"}
        | _nested("content[].addedBy", _PERMISSION_DETAIL)
    )

    assert header.status_code == 200
    assert _paths(header.json()) == log_header_shape
    assert header.json()["referenceNumber"].startswith("PUB-")


async def test_golden_error_bodies() -> None:
    async with client_with_repos() as (client, project_repo, proposal_repo, _):
        not_found = await client.get("/api/v1/collection-use-projects/missing")

        await proposal_repo.add(_proposal(status="REJECTED"))
        await project_repo.add(_project(status=UseStatus.CREATED))
        conflict = await client.post(
            "/api/v1/proposals/prop-1/cancel",
            json={"reason": "No longer needed"},
        )

    assert not_found.status_code == 404
    assert not_found.json() == {
        "error": "PROJECT_NOT_FOUND",
        "message": "No project found with id missing",
    }

    assert conflict.status_code == 409
    assert conflict.json() == {
        "error": "INVALID_TRANSITION",
        "message": "Cannot cancel a rejected proposal",
    }


async def test_golden_access_denied_body() -> None:
    async with client_with_repos(caller=_CALLER) as (
        client,
        project_repo,
        proposal_repo,
        _,
    ):
        from app.use_of_collections.domain.models import PermissionId

        await proposal_repo.add(
            _proposal(requested_by=PermissionId("someone-else"))
        )

        response = await client.get("/api/v1/proposals/prop-1")

    assert response.status_code == 403
    assert response.json() == {
        "error": "ACCESS_DENIED",
        "message": "You do not have access to this proposal",
    }
