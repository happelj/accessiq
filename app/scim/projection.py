from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from fastapi import status

from .errors import raise_scim_error

ATTRIBUTE_PATH_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_.:$-]*$")
ALWAYS_RETURNED_ATTRIBUTES = frozenset({"schemas", "id"})


@dataclass(frozen=True)
class ScimProjection:
    attributes: frozenset[str] | None = None
    excluded_attributes: frozenset[str] = frozenset()


def parse_attribute_projection(
    *,
    attributes: str | None,
    excluded_attributes: str | None,
) -> ScimProjection:
    return ScimProjection(
        attributes=_parse_attribute_list(
            query_name="attributes",
            raw_value=attributes,
            allow_empty=True,
        ),
        excluded_attributes=_parse_attribute_list(
            query_name="excludedAttributes",
            raw_value=excluded_attributes,
            allow_empty=True,
        )
        or frozenset(),
    )


def apply_attribute_projection(
    resource: dict[str, Any],
    projection: ScimProjection,
) -> dict[str, Any]:
    canonical_keys = {key.lower(): key for key in resource}

    if projection.attributes is None:
        selected_keys = set(resource)
    else:
        selected_keys = set()
        for attribute in projection.attributes:
            key = _resolve_resource_key(attribute, canonical_keys)
            if key is not None:
                selected_keys.add(key)

        for attribute in ALWAYS_RETURNED_ATTRIBUTES:
            key = _resolve_resource_key(attribute, canonical_keys)
            if key is not None:
                selected_keys.add(key)

    for attribute in projection.excluded_attributes:
        normalized_attribute = _top_level_attribute(attribute)
        if normalized_attribute in ALWAYS_RETURNED_ATTRIBUTES:
            continue

        key = _resolve_resource_key(attribute, canonical_keys)
        if key is not None:
            selected_keys.discard(key)

    return {key: value for key, value in resource.items() if key in selected_keys}


def _parse_attribute_list(
    *,
    query_name: str,
    raw_value: str | None,
    allow_empty: bool,
) -> frozenset[str] | None:
    if raw_value is None:
        return None

    if raw_value == "" and allow_empty:
        return frozenset()

    attributes: set[str] = set()
    for raw_attribute in raw_value.split(","):
        attribute = raw_attribute.strip()
        if not attribute:
            raise_scim_error(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{query_name} contains an empty attribute path",
                scim_type="invalidPath",
            )

        if ATTRIBUTE_PATH_PATTERN.match(attribute) is None:
            raise_scim_error(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{query_name} contains an invalid attribute path",
                scim_type="invalidPath",
            )

        attributes.add(attribute)

    return frozenset(attributes)


def _resolve_resource_key(
    attribute: str,
    canonical_keys: dict[str, str],
) -> str | None:
    return canonical_keys.get(_top_level_attribute(attribute).lower())


def _top_level_attribute(attribute: str) -> str:
    return attribute.split(".", maxsplit=1)[0]
