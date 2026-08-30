from datetime import UTC, date, datetime
from typing import cast

import pytest

from app.identity.public import Actor, GroupName
from app.shared.exceptions import InsufficientGroup
from app.use_of_collections.application.ports import (
    ProjectFilters,
    ProposalRepository,
    StaffProjectTodoPostit,
)
from app.use_of_collections.application.use_cases import (
    CompleteStaffProjectTodo,
    CreateStaffProjectTodo,
    CreateStaffProjectTodoInput,
    DeleteStaffProjectTodo,
    DeleteStaffProjectTodoInput,
    ListMyStaffProjectTodoPostits,
    ListMyStaffProjectTodoPostitsInput,
    ListStaffProjectTodos,
    ListStaffProjectTodosInput,
    ToggleStaffProjectTodoInput,
    UpdateStaffProjectTodo,
    UpdateStaffProjectTodoInput,
)
from app.use_of_collections.domain.enums import UseStatus, UseType
from app.use_of_collections.domain.models import (
    CollectionUseProject,
    CollectionUseProjectId,
    PermissionId,
    Proposal,
    ProposalId,
    ReferenceNumber,
    StaffProjectTodoItem,
    StaffProjectTodoItemId,
)

NOW = datetime(2026, 8, 11, 10, 0, tzinfo=UTC)

CURATOR_BOB = Actor(
    id=PermissionId("perm-bob-curatorial"),
    group=GroupName.CURATORIAL,
    email="bob@example.test",
)
COLLECTIONS_BOB = Actor(
    id=PermissionId("perm-bob-collections"),
    group=GroupName.COLLECTIONS_MANAGEMENT,
    email="bob@example.test",
)
EXTERNAL_ALICE = Actor(
    id=PermissionId("perm-alice"),
    group=GroupName.EXTERNAL,
    email="alice@example.test",
)


def _project() -> CollectionUseProject:
    return CollectionUseProject(
        id=CollectionUseProjectId("project-1"),
        reference_number=ReferenceNumber("CUP-TODO001"),
        title="Project",
        purpose="Study",
        intended_use=UseType.IN_SITU_VISIT,
        status=UseStatus.CREATED,
        begin_date=date(2026, 8, 11),
        end_date=date(2026, 8, 12),
        requested_by=PermissionId("perm-alice"),
        proposal_id=ProposalId("proposal-1"),
    )


class InMemoryProjectRepository:
    def __init__(self) -> None:
        self.items = {"project-1": _project()}

    async def add(self, project: CollectionUseProject) -> None:
        self.items[project.id] = project

    async def get_by_id(
        self, project_id: CollectionUseProjectId
    ) -> CollectionUseProject | None:
        return self.items.get(project_id)

    async def get_by_reference(
        self, reference_number: ReferenceNumber
    ) -> CollectionUseProject | None:
        return next(
            (
                project
                for project in self.items.values()
                if project.reference_number == reference_number
            ),
            None,
        )

    async def save(self, project: CollectionUseProject) -> None:
        self.items[project.id] = project

    async def list(
        self, filters: ProjectFilters, page: int, size: int
    ) -> tuple[list[CollectionUseProject], int]:
        return list(self.items.values())[page * size : page * size + size], len(
            self.items
        )


class InMemoryProposalRepository:
    async def get_by_project_id(
        self, project_id: CollectionUseProjectId
    ) -> Proposal | None:
        return None


class InMemoryTodoRepository:
    def __init__(self, project_repo: InMemoryProjectRepository) -> None:
        self.project_repo = project_repo
        self.items: dict[str, StaffProjectTodoItem] = {}

    async def list_for_project_and_owner(
        self,
        project_id: CollectionUseProjectId,
        owner_permission_id: str,
    ) -> list[StaffProjectTodoItem]:
        return sorted(
            [
                item
                for item in self.items.values()
                if item.project_id == project_id
                and item.owner_permission_id == owner_permission_id
            ],
            key=lambda item: (item.position, item.created_at, item.id),
        )

    async def get_by_id(
        self, item_id: StaffProjectTodoItemId
    ) -> StaffProjectTodoItem | None:
        return self.items.get(item_id)

    async def list_dashboard_items_for_owner(
        self,
        owner_permission_id: str,
        completed: bool | None,
        project_id: CollectionUseProjectId | None,
        order_by_project: bool,
        offset: int,
        limit: int,
    ) -> tuple[list[StaffProjectTodoPostit], int]:
        items = [
            item
            for item in self.items.values()
            if item.owner_permission_id == owner_permission_id
            and (completed is None or item.completed is completed)
            and (project_id is None or item.project_id == project_id)
        ]
        if order_by_project:
            items.sort(
                key=lambda item: (
                    self.project_repo.items[item.project_id].reference_number.value,
                    item.position,
                    item.created_at,
                    item.id,
                )
            )
        else:
            items.sort(
                key=lambda item: (item.updated_at, item.created_at, item.id),
                reverse=True,
            )
        total = len(items)
        postits: list[StaffProjectTodoPostit] = []
        for item in items[offset : offset + limit]:
            project = self.project_repo.items[item.project_id]
            postits.append(
                StaffProjectTodoPostit(
                    id=item.id,
                    project_id=item.project_id,
                    project_reference_number=project.reference_number,
                    project_title=project.title,
                    project_status=project.status.value,
                    text=item.text,
                    completed=item.completed,
                    created_at=item.created_at,
                    updated_at=item.updated_at,
                    completed_at=item.completed_at,
                    position=item.position,
                )
            )
        return postits, total

    async def add(self, item: StaffProjectTodoItem) -> None:
        self.items[item.id] = item

    async def save(self, item: StaffProjectTodoItem) -> None:
        self.items[item.id] = item

    async def delete(self, item: StaffProjectTodoItem) -> None:
        self.items.pop(item.id, None)

    async def next_position(
        self,
        project_id: CollectionUseProjectId,
        owner_permission_id: str,
    ) -> int:
        positions = [
            item.position
            for item in self.items.values()
            if item.project_id == project_id
            and item.owner_permission_id == owner_permission_id
        ]
        return (max(positions) if positions else 0) + 10


def _use_cases() -> tuple[
    InMemoryTodoRepository,
    InMemoryProjectRepository,
    ProposalRepository,
]:
    project_repo = InMemoryProjectRepository()
    todo_repo = InMemoryTodoRepository(project_repo)
    proposal_repo = InMemoryProposalRepository()
    return todo_repo, project_repo, cast(ProposalRepository, proposal_repo)


async def test_todo_items_are_isolated_by_staff_permission() -> None:
    todo_repo, project_repo, proposal_repo = _use_cases()

    created = await CreateStaffProjectTodo(
        todo_repo, project_repo, proposal_repo
    ).execute(
        CreateStaffProjectTodoInput(
            caller=CURATOR_BOB,
            project_id=CollectionUseProjectId("project-1"),
            text="Confirm handling conditions",
            now=NOW,
        )
    )

    collections_items = await ListStaffProjectTodos(
        todo_repo, project_repo, proposal_repo
    ).execute(
        ListStaffProjectTodosInput(
            caller=COLLECTIONS_BOB,
            project_id=CollectionUseProjectId("project-1"),
        )
    )
    curator_items = await ListStaffProjectTodos(
        todo_repo, project_repo, proposal_repo
    ).execute(
        ListStaffProjectTodosInput(
            caller=CURATOR_BOB,
            project_id=CollectionUseProjectId("project-1"),
        )
    )

    assert collections_items == []
    assert [item.id for item in curator_items] == [created.id]
    assert curator_items[0].owner_permission_id == "perm-bob-curatorial"


async def test_todo_update_toggle_and_delete_require_item_owner() -> None:
    todo_repo, project_repo, proposal_repo = _use_cases()
    created = await CreateStaffProjectTodo(
        todo_repo, project_repo, proposal_repo
    ).execute(
        CreateStaffProjectTodoInput(
            caller=CURATOR_BOB,
            project_id=CollectionUseProjectId("project-1"),
            text="Initial text",
            now=NOW,
        )
    )

    with pytest.raises(LookupError):
        await UpdateStaffProjectTodo(todo_repo, project_repo, proposal_repo).execute(
            UpdateStaffProjectTodoInput(
                caller=COLLECTIONS_BOB,
                project_id=CollectionUseProjectId("project-1"),
                item_id=created.id,
                text="Wrong owner",
                update_text=True,
                now=NOW,
            )
        )

    completed = await CompleteStaffProjectTodo(
        todo_repo, project_repo, proposal_repo
    ).execute(
        ToggleStaffProjectTodoInput(
            caller=CURATOR_BOB,
            project_id=CollectionUseProjectId("project-1"),
            item_id=created.id,
            now=NOW,
        )
    )

    assert completed.completed is True
    assert completed.completed_at == NOW

    await DeleteStaffProjectTodo(todo_repo, project_repo, proposal_repo).execute(
        DeleteStaffProjectTodoInput(
            caller=CURATOR_BOB,
            project_id=CollectionUseProjectId("project-1"),
            item_id=created.id,
        )
    )
    assert todo_repo.items == {}


async def test_external_callers_cannot_use_project_todos() -> None:
    todo_repo, project_repo, proposal_repo = _use_cases()

    with pytest.raises(InsufficientGroup):
        await ListStaffProjectTodos(todo_repo, project_repo, proposal_repo).execute(
            ListStaffProjectTodosInput(
                caller=EXTERNAL_ALICE,
                project_id=CollectionUseProjectId("project-1"),
            )
        )


async def test_dashboard_postits_list_only_current_staff_profile_items() -> None:
    todo_repo, project_repo, proposal_repo = _use_cases()
    project_repo.items["project-2"] = CollectionUseProject(
        id=CollectionUseProjectId("project-2"),
        reference_number=ReferenceNumber("CUP-TODO002"),
        title="Second project",
        purpose="Loan support",
        intended_use=UseType.EXHIBITION,
        status=UseStatus.IN_PROGRESS,
        begin_date=date(2026, 8, 13),
        end_date=date(2026, 8, 14),
        requested_by=PermissionId("perm-alice"),
        proposal_id=ProposalId("proposal-2"),
    )

    curator_first = await CreateStaffProjectTodo(
        todo_repo, project_repo, proposal_repo
    ).execute(
        CreateStaffProjectTodoInput(
            caller=CURATOR_BOB,
            project_id=CollectionUseProjectId("project-1"),
            text="Prepare condition notes",
            now=NOW,
        )
    )
    curator_second = await CreateStaffProjectTodo(
        todo_repo, project_repo, proposal_repo
    ).execute(
        CreateStaffProjectTodoInput(
            caller=CURATOR_BOB,
            project_id=CollectionUseProjectId("project-2"),
            text="Confirm display requirements",
            now=NOW.replace(hour=11),
        )
    )
    await CompleteStaffProjectTodo(todo_repo, project_repo, proposal_repo).execute(
        ToggleStaffProjectTodoInput(
            caller=CURATOR_BOB,
            project_id=CollectionUseProjectId("project-1"),
            item_id=curator_first.id,
            now=NOW.replace(hour=12),
        )
    )
    await CreateStaffProjectTodo(todo_repo, project_repo, proposal_repo).execute(
        CreateStaffProjectTodoInput(
            caller=COLLECTIONS_BOB,
            project_id=CollectionUseProjectId("project-2"),
            text="Reserve handling kit",
            now=NOW.replace(hour=13),
        )
    )

    page = await ListMyStaffProjectTodoPostits(todo_repo).execute(
        ListMyStaffProjectTodoPostitsInput(
            caller=CURATOR_BOB,
            completed=False,
            size=20,
        )
    )

    assert [postit.id for postit in page.items] == [curator_second.id]
    assert page.total == 1
    assert page.items[0].project_id == "project-2"
    assert page.items[0].project_reference_number.value == "CUP-TODO002"
    assert page.items[0].project_title == "Second project"
    assert page.items[0].project_status == UseStatus.IN_PROGRESS.value

    # The project filter narrows the same owner's list to one project.
    filtered = await ListMyStaffProjectTodoPostits(todo_repo).execute(
        ListMyStaffProjectTodoPostitsInput(
            caller=CURATOR_BOB,
            completed=None,
            project_id=CollectionUseProjectId("project-1"),
        )
    )
    assert [postit.id for postit in filtered.items] == [curator_first.id]
    assert filtered.total == 1


async def test_dashboard_postits_paginate_and_order_by_project() -> None:
    todo_repo, project_repo, proposal_repo = _use_cases()
    project_repo.items["project-2"] = CollectionUseProject(
        id=CollectionUseProjectId("project-2"),
        reference_number=ReferenceNumber("CUP-TODO002"),
        title="Second project",
        purpose="Loan support",
        intended_use=UseType.EXHIBITION,
        status=UseStatus.IN_PROGRESS,
        begin_date=date(2026, 8, 13),
        end_date=date(2026, 8, 14),
        requested_by=PermissionId("perm-alice"),
        proposal_id=ProposalId("proposal-2"),
    )

    # Created newest-first against project order, so the two sorts disagree.
    second = await CreateStaffProjectTodo(
        todo_repo, project_repo, proposal_repo
    ).execute(
        CreateStaffProjectTodoInput(
            caller=CURATOR_BOB,
            project_id=CollectionUseProjectId("project-2"),
            text="On the second project",
            now=NOW,
        )
    )
    first = await CreateStaffProjectTodo(
        todo_repo, project_repo, proposal_repo
    ).execute(
        CreateStaffProjectTodoInput(
            caller=CURATOR_BOB,
            project_id=CollectionUseProjectId("project-1"),
            text="On the first project",
            now=NOW.replace(hour=11),
        )
    )

    by_recency = await ListMyStaffProjectTodoPostits(todo_repo).execute(
        ListMyStaffProjectTodoPostitsInput(caller=CURATOR_BOB, completed=False)
    )
    assert [postit.id for postit in by_recency.items] == [first.id, second.id]

    by_project = await ListMyStaffProjectTodoPostits(todo_repo).execute(
        ListMyStaffProjectTodoPostitsInput(
            caller=CURATOR_BOB, completed=False, order_by_project=True
        )
    )
    assert [postit.id for postit in by_project.items] == [first.id, second.id]

    # A page reports the full total, not the slice it returned.
    page_two = await ListMyStaffProjectTodoPostits(todo_repo).execute(
        ListMyStaffProjectTodoPostitsInput(
            caller=CURATOR_BOB, completed=False, page=1, size=1, order_by_project=True
        )
    )
    assert [postit.id for postit in page_two.items] == [second.id]
    assert page_two.total == 2


def test_todo_text_is_trimmed_and_limited() -> None:
    item = StaffProjectTodoItem(
        id=StaffProjectTodoItemId("todo-1"),
        project_id=CollectionUseProjectId("project-1"),
        owner_permission_id=PermissionId("perm-bob-curatorial"),
        text="  Confirm labels  ",
        completed=False,
        created_at=NOW,
        updated_at=NOW,
    )

    assert item.text == "Confirm labels"
    with pytest.raises(ValueError, match="at most 160"):
        item.rename("x" * 161, NOW)
