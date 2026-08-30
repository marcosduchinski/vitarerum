from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from app.identity.public import Actor
from app.shared.authorization import require_staff
from app.use_of_collections.application.authorization import assert_project_access
from app.use_of_collections.application.ports import (
    CollectionUseProjectRepository,
    ProposalRepository,
    StaffProjectTodoPostit,
    StaffProjectTodoRepository,
)
from app.use_of_collections.domain.models import (
    CollectionUseProjectId,
    PermissionId,
    StaffProjectTodoItem,
    StaffProjectTodoItemId,
)


@dataclass(slots=True)
class ListStaffProjectTodosInput:
    caller: Actor
    project_id: CollectionUseProjectId


@dataclass(slots=True)
class CreateStaffProjectTodoInput:
    caller: Actor
    project_id: CollectionUseProjectId
    text: str
    now: datetime


@dataclass(slots=True)
class UpdateStaffProjectTodoInput:
    caller: Actor
    project_id: CollectionUseProjectId
    item_id: StaffProjectTodoItemId
    now: datetime
    text: str | None = None
    update_text: bool = False
    position: int | None = None
    update_position: bool = False


@dataclass(slots=True)
class ToggleStaffProjectTodoInput:
    caller: Actor
    project_id: CollectionUseProjectId
    item_id: StaffProjectTodoItemId
    now: datetime


@dataclass(slots=True)
class DeleteStaffProjectTodoInput:
    caller: Actor
    project_id: CollectionUseProjectId
    item_id: StaffProjectTodoItemId


@dataclass(slots=True)
class ListMyStaffProjectTodoPostitsInput:
    caller: Actor
    completed: bool | None = False
    project_id: CollectionUseProjectId | None = None
    # 'recent' (the dashboard widget's order) vs 'project'. Grouping a paginated
    # list by project only works when the server orders by it too, or a project's
    # items straddle page boundaries.
    order_by_project: bool = False
    page: int = 0
    size: int = 20


@dataclass(slots=True)
class StaffProjectTodoPostitPage:
    items: list[StaffProjectTodoPostit]
    total: int


async def _assert_project_access(
    *,
    caller: Actor,
    project_id: CollectionUseProjectId,
    project_repository: CollectionUseProjectRepository,
    proposal_repository: ProposalRepository,
) -> None:
    require_staff(caller)
    project = await project_repository.get_by_id(project_id)
    if project is None:
        raise LookupError(f"No project found with id {project_id}")
    proposal = await proposal_repository.get_by_project_id(project_id)
    assert_project_access(caller, project, proposal)


def _owner_id(caller: Actor) -> PermissionId:
    if caller.id is None:
        raise PermissionError("A staff permission is required")
    return PermissionId(caller.id)


async def _load_owned_item(
    *,
    todo_repository: StaffProjectTodoRepository,
    caller: Actor,
    project_id: CollectionUseProjectId,
    item_id: StaffProjectTodoItemId,
) -> StaffProjectTodoItem:
    item = await todo_repository.get_by_id(item_id)
    if (
        item is None
        or item.project_id != project_id
        or item.owner_permission_id != _owner_id(caller)
    ):
        raise LookupError(f"No TODO item found with id {item_id}")
    return item


class ListStaffProjectTodos:
    def __init__(
        self,
        todo_repository: StaffProjectTodoRepository,
        project_repository: CollectionUseProjectRepository,
        proposal_repository: ProposalRepository,
    ) -> None:
        self._todo_repository = todo_repository
        self._project_repository = project_repository
        self._proposal_repository = proposal_repository

    async def execute(
        self, data: ListStaffProjectTodosInput
    ) -> list[StaffProjectTodoItem]:
        await _assert_project_access(
            caller=data.caller,
            project_id=data.project_id,
            project_repository=self._project_repository,
            proposal_repository=self._proposal_repository,
        )
        return await self._todo_repository.list_for_project_and_owner(
            data.project_id, _owner_id(data.caller)
        )


class ListMyStaffProjectTodoPostits:
    def __init__(self, todo_repository: StaffProjectTodoRepository) -> None:
        self._todo_repository = todo_repository

    async def execute(
        self, data: ListMyStaffProjectTodoPostitsInput
    ) -> StaffProjectTodoPostitPage:
        require_staff(data.caller)
        if data.size < 1 or data.size > 100:
            raise ValueError("size must be between 1 and 100")
        if data.page < 0:
            raise ValueError("page must be greater than or equal to 0")
        items, total = await self._todo_repository.list_dashboard_items_for_owner(
            _owner_id(data.caller),
            completed=data.completed,
            project_id=data.project_id,
            order_by_project=data.order_by_project,
            offset=data.page * data.size,
            limit=data.size,
        )
        return StaffProjectTodoPostitPage(items=items, total=total)


class CreateStaffProjectTodo:
    def __init__(
        self,
        todo_repository: StaffProjectTodoRepository,
        project_repository: CollectionUseProjectRepository,
        proposal_repository: ProposalRepository,
    ) -> None:
        self._todo_repository = todo_repository
        self._project_repository = project_repository
        self._proposal_repository = proposal_repository

    async def execute(self, data: CreateStaffProjectTodoInput) -> StaffProjectTodoItem:
        await _assert_project_access(
            caller=data.caller,
            project_id=data.project_id,
            project_repository=self._project_repository,
            proposal_repository=self._proposal_repository,
        )
        owner_id = _owner_id(data.caller)
        item = StaffProjectTodoItem(
            id=StaffProjectTodoItemId(str(uuid4())),
            project_id=data.project_id,
            owner_permission_id=owner_id,
            text=data.text,
            completed=False,
            created_at=data.now,
            updated_at=data.now,
            position=await self._todo_repository.next_position(
                data.project_id, owner_id
            ),
        )
        await self._todo_repository.add(item)
        return item


class UpdateStaffProjectTodo:
    def __init__(
        self,
        todo_repository: StaffProjectTodoRepository,
        project_repository: CollectionUseProjectRepository,
        proposal_repository: ProposalRepository,
    ) -> None:
        self._todo_repository = todo_repository
        self._project_repository = project_repository
        self._proposal_repository = proposal_repository

    async def execute(self, data: UpdateStaffProjectTodoInput) -> StaffProjectTodoItem:
        await _assert_project_access(
            caller=data.caller,
            project_id=data.project_id,
            project_repository=self._project_repository,
            proposal_repository=self._proposal_repository,
        )
        item = await _load_owned_item(
            todo_repository=self._todo_repository,
            caller=data.caller,
            project_id=data.project_id,
            item_id=data.item_id,
        )
        if data.update_text:
            if data.text is None:
                raise ValueError("text is required")
            item.rename(data.text, data.now)
        if data.update_position:
            if data.position is None:
                raise ValueError("position is required")
            item.move_to(data.position, data.now)
        await self._todo_repository.save(item)
        return item


class CompleteStaffProjectTodo:
    def __init__(
        self,
        todo_repository: StaffProjectTodoRepository,
        project_repository: CollectionUseProjectRepository,
        proposal_repository: ProposalRepository,
    ) -> None:
        self._todo_repository = todo_repository
        self._project_repository = project_repository
        self._proposal_repository = proposal_repository

    async def execute(self, data: ToggleStaffProjectTodoInput) -> StaffProjectTodoItem:
        await _assert_project_access(
            caller=data.caller,
            project_id=data.project_id,
            project_repository=self._project_repository,
            proposal_repository=self._proposal_repository,
        )
        item = await _load_owned_item(
            todo_repository=self._todo_repository,
            caller=data.caller,
            project_id=data.project_id,
            item_id=data.item_id,
        )
        item.mark_completed(data.now)
        await self._todo_repository.save(item)
        return item


class ReopenStaffProjectTodo:
    def __init__(
        self,
        todo_repository: StaffProjectTodoRepository,
        project_repository: CollectionUseProjectRepository,
        proposal_repository: ProposalRepository,
    ) -> None:
        self._todo_repository = todo_repository
        self._project_repository = project_repository
        self._proposal_repository = proposal_repository

    async def execute(self, data: ToggleStaffProjectTodoInput) -> StaffProjectTodoItem:
        await _assert_project_access(
            caller=data.caller,
            project_id=data.project_id,
            project_repository=self._project_repository,
            proposal_repository=self._proposal_repository,
        )
        item = await _load_owned_item(
            todo_repository=self._todo_repository,
            caller=data.caller,
            project_id=data.project_id,
            item_id=data.item_id,
        )
        item.mark_open(data.now)
        await self._todo_repository.save(item)
        return item


class DeleteStaffProjectTodo:
    def __init__(
        self,
        todo_repository: StaffProjectTodoRepository,
        project_repository: CollectionUseProjectRepository,
        proposal_repository: ProposalRepository,
    ) -> None:
        self._todo_repository = todo_repository
        self._project_repository = project_repository
        self._proposal_repository = proposal_repository

    async def execute(self, data: DeleteStaffProjectTodoInput) -> None:
        await _assert_project_access(
            caller=data.caller,
            project_id=data.project_id,
            project_repository=self._project_repository,
            proposal_repository=self._proposal_repository,
        )
        item = await _load_owned_item(
            todo_repository=self._todo_repository,
            caller=data.caller,
            project_id=data.project_id,
            item_id=data.item_id,
        )
        await self._todo_repository.delete(item)
