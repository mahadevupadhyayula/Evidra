import pytest
from django.db import IntegrityError

from apps.previews.models import ReadinessPreview, ReadinessPreviewStatus
from tests.previews.helpers import make_matching_ready_sprint


@pytest.mark.django_db
def test_one_current_preview_per_revision():
    _user, sprint, *_rest = make_matching_ready_sprint()
    ReadinessPreview.objects.create(
        sprint=sprint,
        role_summary="Role",
        prepkit_explanation="Prep Kit",
        input_revision="same",
        status=ReadinessPreviewStatus.READY,
    )
    with pytest.raises(IntegrityError):
        ReadinessPreview.objects.create(
            sprint=sprint,
            role_summary="Role",
            prepkit_explanation="Prep Kit",
            input_revision="same",
            status=ReadinessPreviewStatus.READY,
        )
