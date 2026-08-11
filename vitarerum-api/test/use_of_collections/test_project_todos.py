from datetime import UTC, date, datetime
from typing import cast

import pytest

from app.identity.public import Actor, GroupName
from app.shared.exceptions import InsufficientGroup
from app.use_of_collections.application.ports import ProjectFilters, ProposalRepository
from app.use_of_collections.application.use_cases import (
    CompleteStaffProjectTodo,
    CreateStaffProjectTodo,
    CreateStaffProjectTodoInput,
    DeleteStaffProjectTodo,
    DeleteStaffProjectTodoInput,
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
    def __init__(self) -> None:
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
    todo_repo = InMemoryTodoRepository()
    project_repo = InMemoryProjectRepository()
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
