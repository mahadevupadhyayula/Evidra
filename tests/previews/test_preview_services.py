import pytest

from ai.client import MockAIClient
from ai.services import EvidraAIService
from apps.previews.models import ReadinessPreview, ReadinessPreviewStatus
from apps.previews.services import ReadinessPreviewError, ReadinessPreviewService
from apps.sprints.models import SprintState
from apps.sprints.services import SprintOwnershipError
from tests.previews.helpers import make_matching_ready_sprint, preview_response


@pytest.mark.django_db
def test_generate_preview_creates_preview_and_transitions_state():
    user, sprint, _profile, evidence, story, _alternative, match = make_matching_ready_sprint()
    client = MockAIClient(responses=[preview_response(match, story, evidence)])
    preview = ReadinessPreviewService.generate_preview(
        user=user, sprint=sprint, ai_service=EvidraAIService(client=client)
    )
    sprint.refresh_from_db()
    assert sprint.state == SprintState.PREVIEW_READY
    assert preview.status == ReadinessPreviewStatus.READY
    assert preview.matched_story_excerpt["story_id"] == story.id


@pytest.mark.django_db
def test_generate_preview_is_idempotent_for_same_revision():
    user, sprint, _profile, evidence, story, _alternative, match = make_matching_ready_sprint()
    client = MockAIClient(responses=[preview_response(match, story, evidence)])
    first = ReadinessPreviewService.generate_preview(
        user=user, sprint=sprint, ai_service=EvidraAIService(client=client)
    )
    second = ReadinessPreviewService.generate_preview(
        user=user, sprint=sprint, ai_service=EvidraAIService(client=MockAIClient())
    )
    assert first.id == second.id
    assert (
        ReadinessPreview.objects.filter(sprint=sprint, status=ReadinessPreviewStatus.READY).count()
        == 1
    )


@pytest.mark.django_db
def test_generate_preview_rejects_cross_user_sprint():
    user, sprint, _profile, _evidence, _story, _alternative, _match = make_matching_ready_sprint()
    other, _other_sprint, *_rest = make_matching_ready_sprint("preview-other@example.com")
    with pytest.raises(SprintOwnershipError):
        ReadinessPreviewService.generate_preview(user=other, sprint=sprint)


@pytest.mark.django_db
def test_generate_preview_rejects_unknown_evidence_reference():
    user, sprint, _profile, evidence, story, _alternative, match = make_matching_ready_sprint()
    data = preview_response(match, story, evidence)
    data["strengths"][0]["evidence_ids"] = [99999]
    with pytest.raises(ReadinessPreviewError):
        ReadinessPreviewService.generate_preview(
            user=user,
            sprint=sprint,
            ai_service=EvidraAIService(client=MockAIClient(responses=[data])),
        )
    sprint.refresh_from_db()
    assert sprint.state == SprintState.MATCHING_READY


@pytest.mark.django_db
def test_generate_preview_stales_prior_ready_preview_when_revision_changes():
    user, sprint, _profile, evidence, story, _alternative, match = make_matching_ready_sprint()
    first = ReadinessPreviewService.generate_preview(
        user=user,
        sprint=sprint,
        ai_service=EvidraAIService(
            client=MockAIClient(responses=[preview_response(match, story, evidence)])
        ),
    )
    story.short_answer = "I led product strategy with a sharper preview excerpt."
    story.save(update_fields=["short_answer", "updated_at"])
    second = ReadinessPreviewService.generate_preview(
        user=user,
        sprint=sprint,
        ai_service=EvidraAIService(
            client=MockAIClient(responses=[preview_response(match, story, evidence)])
        ),
    )
    first.refresh_from_db()
    assert first.status == ReadinessPreviewStatus.STALE
    assert second.status == ReadinessPreviewStatus.READY
    assert second.id != first.id
