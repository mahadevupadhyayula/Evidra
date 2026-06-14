from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from apps.opportunities.models import RoleFamily


class RolePackError(RuntimeError):
    """Raised when a fixed role pack is missing or malformed."""


class RolePack(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    label: str
    competencies: list[str] = Field(min_length=1, max_length=12)
    skills: list[str] = Field(default_factory=list, max_length=20)
    seniority_expectations: list[str] = Field(default_factory=list, max_length=12)
    likely_themes: list[str] = Field(default_factory=list, max_length=12)


ROLE_PACK_FILES = {
    RoleFamily.PRODUCT_MANAGEMENT: "product_management.yaml",
    RoleFamily.AI_PRODUCT_MANAGEMENT: "ai_product_management.yaml",
    RoleFamily.SOFTWARE_ENGINEERING: "software_engineering.yaml",
    RoleFamily.DATA_ANALYTICS: "data_analytics.yaml",
    RoleFamily.SALES_BUSINESS_DEVELOPMENT: "sales_business_development.yaml",
    RoleFamily.CONSULTING_STRATEGY_OPS: "consulting_strategy_ops.yaml",
    RoleFamily.OTHER: "other.yaml",
}


@lru_cache(maxsize=len(ROLE_PACK_FILES))
def get_role_pack(role_family: str | RoleFamily) -> RolePack:
    try:
        family = RoleFamily(role_family)
    except ValueError as exc:
        raise RolePackError("Unsupported role family.") from exc

    filename = ROLE_PACK_FILES.get(family)
    if filename is None:
        raise RolePackError("Role pack is not configured.")

    path = Path(__file__).resolve().parent / "role_packs" / filename
    try:
        raw_data = _load_fixed_role_pack_yaml(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RolePackError("Role pack file could not be loaded.") from exc
    raw_data.setdefault("key", family.value)
    raw_data.setdefault("label", family.label)
    try:
        role_pack = RolePack.model_validate(raw_data)
    except ValidationError as exc:
        raise RolePackError("Role pack is malformed.") from exc
    if role_pack.key != family.value:
        raise RolePackError("Role pack key does not match role family.")
    return role_pack


def role_pack_as_prompt_context(role_pack: RolePack) -> dict[str, Any]:
    return role_pack.model_dump()


def _load_fixed_role_pack_yaml(content: str) -> dict[str, object]:
    """Parse the constrained fixed role-pack YAML shape used by this stage."""

    data: dict[str, object] = {}
    current_list_key: str | None = None
    for raw_line in content.splitlines():
        line = raw_line.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith("  - "):
            if current_list_key is None:
                raise RolePackError("Role pack list item is outside a list field.")
            values = data.setdefault(current_list_key, [])
            if not isinstance(values, list):
                raise RolePackError("Role pack field is malformed.")
            value = line[4:].strip()
            if value:
                values.append(value)
            continue
        if line.startswith(" "):
            raise RolePackError("Role pack contains unsupported indentation.")
        if ":" not in line:
            raise RolePackError("Role pack line is malformed.")
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            raise RolePackError("Role pack field is malformed.")
        if value:
            data[key] = value
            current_list_key = None
        else:
            data[key] = []
            current_list_key = key
    return data
