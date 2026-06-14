import pytest

from apps.opportunities.models import RoleFamily
from apps.opportunities.role_packs import RolePackError, get_role_pack


@pytest.mark.django_db
def test_every_role_family_has_role_pack():
    for value, label in RoleFamily.choices:
        role_pack = get_role_pack(value)
        assert role_pack.key == value
        assert role_pack.label == label
        assert role_pack.competencies


@pytest.mark.django_db
def test_role_pack_rejects_invalid_family():
    with pytest.raises(RolePackError):
        get_role_pack("../../secrets")
