from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.sql.elements import ColumnElement

from ..domain.events import (
    DomainEvent,
    GroupCreated,
    GroupMembershipAdded,
    GroupMembershipRemoved,
    GroupMembershipReplaced,
    GroupUpdated,
    event_time,
)
from ..domain.publisher import publish_domain_events
from ..models import Group, GroupMember, User

SUPPORTED_GROUP_SORT_FIELDS: dict[str, ColumnElement[Any]] = {
    "id": Group.id,
    "displayName": func.lower(Group.display_name),
}
SUPPORTED_GROUP_SORT_ORDERS = {"ascending", "descending"}


@dataclass(frozen=True)
class GroupPatchOperation:
    op: Literal["add", "remove", "replace"]
    path: Literal["displayName", "members"]
    value: Any = None


class GroupServiceError(Exception):
    """Base exception for reusable group service failures."""


class DuplicateGroupError(GroupServiceError):
    def __init__(self, display_name: str, existing_group: Group) -> None:
        super().__init__(f"Group with displayName {display_name!r} already exists")
        self.display_name = display_name
        self.existing_group = existing_group


class GroupNotFoundError(GroupServiceError):
    def __init__(self, group_id: str) -> None:
        super().__init__(f"Group {group_id!r} was not found")
        self.group_id = group_id


class UnknownGroupMemberError(GroupServiceError):
    def __init__(self, user_id: str) -> None:
        super().__init__(f"Group member {user_id!r} was not found")
        self.user_id = user_id


class DuplicateGroupMemberError(GroupServiceError):
    def __init__(self, user_id: str) -> None:
        super().__init__(f"Group member {user_id!r} is already present")
        self.user_id = user_id


class UnsupportedGroupSortFieldError(GroupServiceError):
    def __init__(self, sort_by: str) -> None:
        super().__init__(f"Unsupported group sort field: {sort_by}")
        self.sort_by = sort_by


class UnsupportedGroupSortOrderError(GroupServiceError):
    def __init__(self, sort_order: str) -> None:
        super().__init__(f"Unsupported group sort order: {sort_order}")
        self.sort_order = sort_order


class GroupService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.pending_events: list[DomainEvent] = []

    def create_group(
        self,
        *,
        display_name: str,
        member_ids: tuple[int, ...] = (),
    ) -> Group:
        self.check_duplicate_group(display_name)
        members = self._require_distinct_users(member_ids)

        group = Group(display_name=display_name)
        self.db.add(group)
        self.db.flush()

        for member in members:
            group.memberships.append(GroupMember(user_id=member.id))

        self.db.flush()
        self.pending_events.append(
            GroupCreated(
                occurred_at=event_time(),
                group_id=group.id,
                display_name=group.display_name,
            )
        )
        if members:
            self.pending_events.append(
                GroupMembershipReplaced(
                    occurred_at=event_time(),
                    group_id=group.id,
                    user_ids=tuple(member.id for member in members),
                )
            )

        return group

    def find_group(self, group_id: str) -> Group | None:
        try:
            parsed_group_id = int(group_id)
        except ValueError:
            return None

        if parsed_group_id < 1:
            return None

        return self.db.get(Group, parsed_group_id)

    def list_groups(
        self,
        *,
        filter_expression: ColumnElement[bool] | None,
        sort_by: str | None,
        sort_order: str | None,
        offset: int,
        limit: int,
    ) -> tuple[int, list[Group]]:
        count_statement = select(func.count(Group.id))
        group_statement: Select[tuple[Group]] = select(Group).options(
            joinedload(Group.memberships).joinedload(GroupMember.user)
        )

        if filter_expression is not None:
            count_statement = count_statement.where(filter_expression)
            group_statement = group_statement.where(filter_expression)

        total_results = self.db.scalar(count_statement) or 0
        group_statement = self._apply_group_sorting(
            group_statement,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        groups = (
            self.db.execute(group_statement.offset(offset).limit(limit))
            .unique()
            .scalars()
            .all()
        )

        return total_results, list(groups)

    def replace_group(
        self,
        group_id: str,
        *,
        display_name: str,
        member_ids: tuple[int, ...],
    ) -> Group:
        group = self._require_group(group_id)
        old_display_name = group.display_name
        self.check_duplicate_group(display_name, current_group=group)

        group.display_name = display_name
        if old_display_name != display_name:
            self.pending_events.append(
                GroupUpdated(
                    occurred_at=event_time(),
                    group_id=group.id,
                    display_name=display_name,
                )
            )

        self._replace_members(group, member_ids)
        self.db.flush()

        return group

    def patch_group(
        self,
        group_id: str,
        operations: list[GroupPatchOperation],
    ) -> Group:
        group = self._require_group(group_id)

        for operation in operations:
            if operation.path == "displayName":
                if operation.op == "remove":
                    raise ValueError("displayName is required and cannot be removed")

                self._rename_group(group, str(operation.value))
                continue

            if operation.op == "replace":
                self._replace_members(group, tuple(operation.value))
            elif operation.op == "add":
                for user_id in tuple(operation.value):
                    self._add_member(group, user_id)
            else:
                for user_id in tuple(operation.value):
                    self._remove_member(group, user_id)

        self.db.flush()

        return group

    def add_member(self, group_id: str, user_id: int) -> Group:
        group = self._require_group(group_id)
        self._add_member(group, user_id)
        self.db.flush()

        return group

    def remove_member(self, group_id: str, user_id: int) -> Group:
        group = self._require_group(group_id)
        self._remove_member(group, user_id)
        self.db.flush()

        return group

    def replace_members(
        self,
        group_id: str,
        member_ids: tuple[int, ...],
    ) -> Group:
        group = self._require_group(group_id)
        self._replace_members(group, member_ids)
        self.db.flush()

        return group

    def list_members(self, group: Group) -> list[User]:
        return [
            membership.user
            for membership in sorted(
                group.memberships,
                key=lambda membership: membership.user_id,
            )
        ]

    def check_duplicate_group(
        self,
        display_name: str,
        *,
        current_group: Group | None = None,
    ) -> None:
        existing_group = self.db.scalar(
            select(Group).where(func.lower(Group.display_name) == display_name.lower())
        )
        if existing_group is None:
            return

        if current_group is not None and existing_group.id == current_group.id:
            return

        raise DuplicateGroupError(display_name, existing_group)

    def publish_pending_events(self) -> None:
        publish_domain_events(self.pending_events)
        self.pending_events.clear()

    def _require_group(self, group_id: str) -> Group:
        group = self.find_group(group_id)
        if group is None:
            raise GroupNotFoundError(group_id)

        return group

    def _rename_group(self, group: Group, display_name: str) -> None:
        if group.display_name == display_name:
            return

        self.check_duplicate_group(display_name, current_group=group)
        group.display_name = display_name
        self.pending_events.append(
            GroupUpdated(
                occurred_at=event_time(),
                group_id=group.id,
                display_name=display_name,
            )
        )

    def _add_member(self, group: Group, user_id: int) -> None:
        user = self._require_user(user_id)
        if self._find_membership(group, user.id) is not None:
            raise DuplicateGroupMemberError(str(user.id))

        group.memberships.append(GroupMember(user_id=user.id))
        self.pending_events.append(
            GroupMembershipAdded(
                occurred_at=event_time(),
                group_id=group.id,
                user_id=user.id,
            )
        )

    def _remove_member(self, group: Group, user_id: int) -> None:
        user = self._require_user(user_id)
        membership = self._find_membership(group, user.id)
        if membership is None:
            raise UnknownGroupMemberError(str(user.id))

        group.memberships.remove(membership)
        self.pending_events.append(
            GroupMembershipRemoved(
                occurred_at=event_time(),
                group_id=group.id,
                user_id=user.id,
            )
        )

    def _replace_members(
        self,
        group: Group,
        member_ids: tuple[int, ...],
    ) -> None:
        members = self._require_distinct_users(member_ids)
        group.memberships.clear()
        for member in members:
            group.memberships.append(GroupMember(user_id=member.id))

        self.pending_events.append(
            GroupMembershipReplaced(
                occurred_at=event_time(),
                group_id=group.id,
                user_ids=tuple(member.id for member in members),
            )
        )

    def _require_distinct_users(self, user_ids: tuple[int, ...]) -> list[User]:
        seen_user_ids: set[int] = set()
        for user_id in user_ids:
            if user_id in seen_user_ids:
                raise DuplicateGroupMemberError(str(user_id))
            seen_user_ids.add(user_id)

        if not user_ids:
            return []

        users = {
            user.id: user
            for user in self.db.scalars(select(User).where(User.id.in_(user_ids))).all()
        }
        for user_id in user_ids:
            if user_id not in users:
                raise UnknownGroupMemberError(str(user_id))

        return [users[user_id] for user_id in user_ids]

    def _require_user(self, user_id: int) -> User:
        user = self.db.get(User, user_id)
        if user is None:
            raise UnknownGroupMemberError(str(user_id))

        return user

    def _find_membership(
        self,
        group: Group,
        user_id: int,
    ) -> GroupMember | None:
        for membership in group.memberships:
            if membership.user_id == user_id:
                return membership

        return None

    def _apply_group_sorting(
        self,
        statement: Select[tuple[Group]],
        *,
        sort_by: str | None,
        sort_order: str | None,
    ) -> Select[tuple[Group]]:
        normalized_sort_order = sort_order or "ascending"
        if normalized_sort_order not in SUPPORTED_GROUP_SORT_ORDERS:
            raise UnsupportedGroupSortOrderError(normalized_sort_order)

        if sort_by is None:
            sort_expression = Group.id
        else:
            sort_expression = SUPPORTED_GROUP_SORT_FIELDS.get(sort_by)
            if sort_expression is None:
                raise UnsupportedGroupSortFieldError(sort_by)

        if normalized_sort_order == "descending":
            return statement.order_by(sort_expression.desc(), Group.id.desc())

        return statement.order_by(sort_expression.asc(), Group.id.asc())
