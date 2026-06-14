import pytest
from django.contrib.auth import get_user_model
from django.http import Http404

from ai.client import AIClientError, MockAIClient
from ai.services import AIJDAnalysisError, EvidraAIService
from apps.opportunities.company_context import CompanyContextFetchError, CompanyContextFetchResult
from apps.opportunities.models import CompanyContextStatus, Opportunity, OpportunityStatus
from apps.opportunities.services import OpportunityError, OpportunityService
from apps.sprints.models import InterviewSprint, SprintState
from apps.sprints.services import InvalidSprintTransition, SprintWorkflowService
from tests.ai.test_company_context_schema import valid_context
from tests.opportunities.helpers import (
    jd_analysis_dict,
    make_profile_confirmed_sprint,
    opportunity_data,
)


@pytest.mark.django_db
def test_analyze_and_save_opportunity_creates_draft_with_analysis():
    user, sprint, _profile = make_profile_confirmed_sprint()
    client = MockAIClient(responses=[jd_analysis_dict()])

    opportunity = OpportunityService.analyze_and_save_opportunity(
        user=user,
        sprint=sprint,
        cleaned_data=opportunity_data(),
        ai_service=EvidraAIService(client=client),
    )

    assert opportunity.sprint == sprint
    assert opportunity.confirmation_status == OpportunityStatus.DRAFT
    assert opportunity.jd_analysis["summary"]
    assert opportunity.role_family == "PRODUCT_MANAGEMENT"
    assert client.calls[0]["role_family"] == "PRODUCT_MANAGEMENT"
    sprint.refresh_from_db()
    assert sprint.state == SprintState.PROFILE_CONFIRMED


@pytest.mark.django_db
def test_analyze_and_save_opportunity_updates_existing_draft():
    user, sprint, _profile = make_profile_confirmed_sprint()
    ai_service = EvidraAIService(
        client=MockAIClient(responses=[jd_analysis_dict(), jd_analysis_dict()])
    )

    first = OpportunityService.analyze_and_save_opportunity(
        user=user,
        sprint=sprint,
        cleaned_data=opportunity_data(role_title="First Title"),
        ai_service=ai_service,
    )
    second = OpportunityService.analyze_and_save_opportunity(
        user=user,
        sprint=sprint,
        cleaned_data=opportunity_data(role_title="Second Title"),
        ai_service=ai_service,
    )

    assert first.pk == second.pk
    assert second.role_title == "Second Title"
    assert Opportunity.objects.filter(sprint=sprint).count() == 1


@pytest.mark.django_db
def test_analyze_rejects_sprint_before_profile_confirmed():
    user = get_user_model().objects.create_user(username="draft@example.com")
    sprint = InterviewSprint.objects.create(user=user, state=SprintState.DRAFT)

    with pytest.raises(InvalidSprintTransition):
        OpportunityService.analyze_and_save_opportunity(
            user=user,
            sprint=sprint,
            cleaned_data=opportunity_data(),
            ai_service=EvidraAIService(client=MockAIClient()),
        )


@pytest.mark.django_db
def test_ai_failure_preserves_draft_and_sprint_state():
    user, sprint, _profile = make_profile_confirmed_sprint()

    with pytest.raises(AIJDAnalysisError):
        OpportunityService.analyze_and_save_opportunity(
            user=user,
            sprint=sprint,
            cleaned_data=opportunity_data(role_title="Saved title"),
            ai_service=EvidraAIService(
                client=MockAIClient(responses=[AIClientError("down"), AIClientError("down")])
            ),
        )

    opportunity = Opportunity.objects.get(sprint=sprint)
    assert opportunity.role_title == "Saved title"
    assert opportunity.jd_analysis is None
    sprint.refresh_from_db()
    assert sprint.state == SprintState.PROFILE_CONFIRMED


@pytest.mark.django_db
def test_failed_reanalysis_clears_stale_analysis_and_blocks_confirmation():
    user, sprint, _profile = make_profile_confirmed_sprint()
    opportunity = OpportunityService.analyze_and_save_opportunity(
        user=user,
        sprint=sprint,
        cleaned_data=opportunity_data(role_title="Original title"),
        ai_service=EvidraAIService(client=MockAIClient(responses=[jd_analysis_dict()])),
    )
    assert opportunity.jd_analysis is not None

    with pytest.raises(AIJDAnalysisError):
        OpportunityService.analyze_and_save_opportunity(
            user=user,
            sprint=sprint,
            cleaned_data=opportunity_data(role_title="Updated title"),
            ai_service=EvidraAIService(
                client=MockAIClient(responses=[AIClientError("down"), AIClientError("down")])
            ),
        )

    opportunity.refresh_from_db()
    assert opportunity.role_title == "Updated title"
    assert opportunity.jd_analysis is None
    with pytest.raises(OpportunityError):
        OpportunityService.confirm_opportunity(
            user=user,
            sprint=sprint,
            opportunity_id=opportunity.pk,
        )
    sprint.refresh_from_db()
    assert sprint.state == SprintState.PROFILE_CONFIRMED


@pytest.mark.django_db
def test_confirm_opportunity_transitions_sprint():
    user, sprint, _profile = make_profile_confirmed_sprint()
    opportunity = OpportunityService.analyze_and_save_opportunity(
        user=user,
        sprint=sprint,
        cleaned_data=opportunity_data(),
        ai_service=EvidraAIService(client=MockAIClient(responses=[jd_analysis_dict()])),
    )

    OpportunityService.skip_company_context(user=user, sprint=sprint, opportunity_id=opportunity.pk)
    OpportunityService.confirm_opportunity(user=user, sprint=sprint, opportunity_id=opportunity.pk)

    opportunity.refresh_from_db()
    sprint.refresh_from_db()
    assert opportunity.confirmation_status == OpportunityStatus.CONFIRMED
    assert opportunity.confirmed_at is not None
    assert sprint.state == SprintState.OPPORTUNITY_CONFIRMED


@pytest.mark.django_db
def test_confirm_opportunity_rejects_missing_analysis():
    user, sprint, _profile = make_profile_confirmed_sprint()
    opportunity = Opportunity.objects.create(sprint=sprint, **opportunity_data())

    with pytest.raises(OpportunityError):
        OpportunityService.confirm_opportunity(
            user=user, sprint=sprint, opportunity_id=opportunity.pk
        )

    sprint.refresh_from_db()
    assert sprint.state == SprintState.PROFILE_CONFIRMED


@pytest.mark.django_db
def test_get_owned_opportunity_rejects_cross_user_access():
    owner, sprint, _profile = make_profile_confirmed_sprint("owner@example.com")
    other = get_user_model().objects.create_user(username="other@example.com")
    opportunity = Opportunity.objects.create(sprint=sprint, **opportunity_data())

    assert opportunity.sprint.user == owner
    with pytest.raises(Http404):
        OpportunityService.get_owned_opportunity(other, opportunity.pk)


@pytest.mark.django_db
def test_mark_opportunity_confirmed_is_idempotent_for_confirmed_sprint():
    user, sprint, _profile = make_profile_confirmed_sprint()
    opportunity = Opportunity.objects.create(
        sprint=sprint,
        confirmation_status=OpportunityStatus.CONFIRMED,
        jd_analysis=jd_analysis_dict(),
        **opportunity_data(),
    )
    SprintWorkflowService.mark_opportunity_confirmed(
        user=user, sprint=sprint, opportunity=opportunity
    )
    sprint.refresh_from_db()

    again = SprintWorkflowService.mark_opportunity_confirmed(
        user=user,
        sprint=sprint,
        opportunity=opportunity,
    )

    assert again.state == SprintState.OPPORTUNITY_CONFIRMED




class FakeCompanyContextFetcher:
    def __init__(self, result=None):
        self.result = result or CompanyContextFetchResult(
            final_url="https://example.com/about",
            visible_text="Example builds collaboration software for product teams.",
            content_type="text/html",
        )
        self.calls = []

    def fetch(self, url):
        self.calls.append(url)
        return self.result


@pytest.mark.django_db
def test_extract_company_context_from_url_stores_pending_review_context():
    user, sprint, _profile = make_profile_confirmed_sprint()
    opportunity = OpportunityService.analyze_and_save_opportunity(
        user=user,
        sprint=sprint,
        cleaned_data=opportunity_data(),
        ai_service=EvidraAIService(client=MockAIClient(responses=[jd_analysis_dict()])),
    )
    fetcher = FakeCompanyContextFetcher()
    ai_service = EvidraAIService(client=MockAIClient(responses=[valid_context()]))

    updated = OpportunityService.extract_company_context_from_url(
        user=user,
        sprint=sprint,
        opportunity_id=opportunity.pk,
        company_url="https://example.com",
        fetcher=fetcher,
        ai_service=ai_service,
    )

    assert fetcher.calls == ["https://example.com"]
    assert updated.company_url == "https://example.com/about"
    assert updated.company_context["company_description"]
    assert updated.company_context_status == CompanyContextStatus.PENDING_REVIEW
    sprint.refresh_from_db()
    assert sprint.state == SprintState.PROFILE_CONFIRMED


@pytest.mark.django_db
def test_extract_company_context_from_paste_does_not_fetch():
    user, sprint, _profile = make_profile_confirmed_sprint()
    opportunity = OpportunityService.analyze_and_save_opportunity(
        user=user,
        sprint=sprint,
        cleaned_data=opportunity_data(),
        ai_service=EvidraAIService(client=MockAIClient(responses=[jd_analysis_dict()])),
    )
    ai_service = EvidraAIService(client=MockAIClient(responses=[valid_context()]))

    updated = OpportunityService.extract_company_context_from_paste(
        user=user,
        sprint=sprint,
        opportunity_id=opportunity.pk,
        pasted_company_context="Example builds collaboration software for product teams.",
        ai_service=ai_service,
    )

    assert updated.company_url == ""
    assert updated.company_context_status == CompanyContextStatus.PENDING_REVIEW


@pytest.mark.django_db
def test_confirm_and_skip_company_context_are_idempotent_paths():
    user, sprint, _profile = make_profile_confirmed_sprint()
    opportunity = OpportunityService.analyze_and_save_opportunity(
        user=user,
        sprint=sprint,
        cleaned_data=opportunity_data(),
        ai_service=EvidraAIService(client=MockAIClient(responses=[jd_analysis_dict()])),
    )
    opportunity.company_context = valid_context()
    opportunity.company_context_status = CompanyContextStatus.PENDING_REVIEW
    opportunity.save(update_fields=["company_context", "company_context_status", "updated_at"])

    confirmed = OpportunityService.confirm_company_context(
        user=user, sprint=sprint, opportunity_id=opportunity.pk
    )
    assert confirmed.company_context_status == CompanyContextStatus.CONFIRMED

    with pytest.raises(OpportunityError):
        OpportunityService.skip_company_context(
            user=user, sprint=sprint, opportunity_id=opportunity.pk
        )


@pytest.mark.django_db
def test_skip_company_context_is_idempotent_before_confirmation():
    user, sprint, _profile = make_profile_confirmed_sprint()
    opportunity = OpportunityService.analyze_and_save_opportunity(
        user=user,
        sprint=sprint,
        cleaned_data=opportunity_data(),
        ai_service=EvidraAIService(client=MockAIClient(responses=[jd_analysis_dict()])),
    )

    first = OpportunityService.skip_company_context(
        user=user, sprint=sprint, opportunity_id=opportunity.pk
    )
    second = OpportunityService.skip_company_context(
        user=user, sprint=sprint, opportunity_id=opportunity.pk
    )

    assert first.company_context_status == CompanyContextStatus.SKIPPED
    assert second.company_context_status == CompanyContextStatus.SKIPPED


class FailingCompanyContextFetcher:
    def fetch(self, url):
        raise CompanyContextFetchError("fetch failed")


@pytest.mark.django_db
def test_fetch_failure_sets_failed_and_preserves_previous_context():
    user, sprint, _profile = make_profile_confirmed_sprint()
    opportunity = OpportunityService.analyze_and_save_opportunity(
        user=user,
        sprint=sprint,
        cleaned_data=opportunity_data(),
        ai_service=EvidraAIService(client=MockAIClient(responses=[jd_analysis_dict()])),
    )
    opportunity.company_context = valid_context()
    opportunity.company_context_status = CompanyContextStatus.CONFIRMED
    opportunity.save(update_fields=["company_context", "company_context_status", "updated_at"])

    with pytest.raises(CompanyContextFetchError):
        OpportunityService.extract_company_context_from_url(
            user=user,
            sprint=sprint,
            opportunity_id=opportunity.pk,
            company_url="https://example.com",
            fetcher=FailingCompanyContextFetcher(),
        )

    opportunity.refresh_from_db()
    assert opportunity.company_context["company_description"]
    assert opportunity.company_context_status == CompanyContextStatus.FAILED


@pytest.mark.django_db
def test_failed_reanalysis_preserves_previous_company_context():
    user, sprint, _profile = make_profile_confirmed_sprint()
    opportunity = OpportunityService.analyze_and_save_opportunity(
        user=user,
        sprint=sprint,
        cleaned_data=opportunity_data(role_title="Original title"),
        ai_service=EvidraAIService(client=MockAIClient(responses=[jd_analysis_dict()])),
    )
    opportunity.company_context = valid_context()
    opportunity.company_context_status = CompanyContextStatus.CONFIRMED
    opportunity.save(update_fields=["company_context", "company_context_status", "updated_at"])

    with pytest.raises(AIJDAnalysisError):
        OpportunityService.analyze_and_save_opportunity(
            user=user,
            sprint=sprint,
            cleaned_data=opportunity_data(role_title="Updated title"),
            ai_service=EvidraAIService(
                client=MockAIClient(responses=[AIClientError("down"), AIClientError("down")])
            ),
        )

    opportunity.refresh_from_db()
    assert opportunity.company_context["company_description"]
    assert opportunity.company_context_status == CompanyContextStatus.CONFIRMED


@pytest.mark.django_db
def test_successful_reanalysis_marks_confirmed_company_context_pending_review():
    user, sprint, _profile = make_profile_confirmed_sprint()
    ai_service = EvidraAIService(
        client=MockAIClient(responses=[jd_analysis_dict(), jd_analysis_dict()])
    )
    opportunity = OpportunityService.analyze_and_save_opportunity(
        user=user,
        sprint=sprint,
        cleaned_data=opportunity_data(role_title="Original title"),
        ai_service=ai_service,
    )
    opportunity.company_context = valid_context()
    opportunity.company_context_status = CompanyContextStatus.CONFIRMED
    opportunity.save(update_fields=["company_context", "company_context_status", "updated_at"])

    OpportunityService.analyze_and_save_opportunity(
        user=user,
        sprint=sprint,
        cleaned_data=opportunity_data(role_title="Updated title"),
        ai_service=ai_service,
    )

    opportunity.refresh_from_db()
    assert opportunity.company_context["company_description"]
    assert opportunity.company_context_status == CompanyContextStatus.PENDING_REVIEW


@pytest.mark.django_db
def test_confirm_opportunity_requires_confirmed_or_skipped_company_context():
    user, sprint, _profile = make_profile_confirmed_sprint()
    opportunity = OpportunityService.analyze_and_save_opportunity(
        user=user,
        sprint=sprint,
        cleaned_data=opportunity_data(),
        ai_service=EvidraAIService(client=MockAIClient(responses=[jd_analysis_dict()])),
    )

    with pytest.raises(OpportunityError):
        OpportunityService.confirm_opportunity(
            user=user, sprint=sprint, opportunity_id=opportunity.pk
        )

    opportunity.company_context = valid_context()
    opportunity.company_context_status = CompanyContextStatus.PENDING_REVIEW
    opportunity.save(update_fields=["company_context", "company_context_status", "updated_at"])
    with pytest.raises(OpportunityError):
        OpportunityService.confirm_opportunity(
            user=user, sprint=sprint, opportunity_id=opportunity.pk
        )

    opportunity.company_context_status = CompanyContextStatus.FAILED
    opportunity.save(update_fields=["company_context_status", "updated_at"])
    with pytest.raises(OpportunityError):
        OpportunityService.confirm_opportunity(
            user=user, sprint=sprint, opportunity_id=opportunity.pk
        )


class InvalidMetadataCompanyContextFetcher:
    def fetch(self, url):
        raise CompanyContextFetchError("Company URL returned invalid response metadata.")


@pytest.mark.django_db
def test_invalid_fetch_metadata_sets_failed_and_preserves_previous_context():
    user, sprint, _profile = make_profile_confirmed_sprint()
    opportunity = OpportunityService.analyze_and_save_opportunity(
        user=user,
        sprint=sprint,
        cleaned_data=opportunity_data(),
        ai_service=EvidraAIService(client=MockAIClient(responses=[jd_analysis_dict()])),
    )
    opportunity.company_context = valid_context()
    opportunity.company_context_status = CompanyContextStatus.CONFIRMED
    opportunity.save(update_fields=["company_context", "company_context_status", "updated_at"])

    with pytest.raises(CompanyContextFetchError):
        OpportunityService.extract_company_context_from_url(
            user=user,
            sprint=sprint,
            opportunity_id=opportunity.pk,
            company_url="https://example.com",
            fetcher=InvalidMetadataCompanyContextFetcher(),
        )

    opportunity.refresh_from_db()
    assert opportunity.company_context["company_description"]
    assert opportunity.company_context_status == CompanyContextStatus.FAILED


@pytest.mark.django_db
def test_update_company_context_review_saves_edits_and_preserves_ownership():
    user, sprint, _profile = make_profile_confirmed_sprint()
    opportunity = OpportunityService.analyze_and_save_opportunity(
        user=user,
        sprint=sprint,
        cleaned_data=opportunity_data(),
        ai_service=EvidraAIService(client=MockAIClient(responses=[jd_analysis_dict()])),
    )
    opportunity.company_context = valid_context()
    opportunity.company_context_status = CompanyContextStatus.PENDING_REVIEW
    opportunity.save(update_fields=["company_context", "company_context_status", "updated_at"])

    updated = OpportunityService.update_company_context_review(
        user=user,
        sprint=sprint,
        opportunity_id=opportunity.pk,
        company_context_payload={
            "company_description": "Example builds collaboration software for product teams.",
            "products_or_services": ["Collaboration software"],
            "target_users": ["Product teams"],
            "business_model_clues": [],
            "product_terminology": [],
            "strategic_themes": [],
            "source_type": "paste",
            "source_url": None,
            "source_references": [],
            "uncertain_fields": [],
        },
    )

    assert updated.company_context["company_description"].startswith("Example builds")
    assert updated.company_context_status == CompanyContextStatus.PENDING_REVIEW


@pytest.mark.django_db
def test_update_company_context_review_rejects_cross_user_access():
    _owner, sprint, _profile = make_profile_confirmed_sprint("owner-review@example.com")
    other, other_sprint, _other_profile = make_profile_confirmed_sprint("other-review@example.com")
    opportunity = Opportunity.objects.create(
        sprint=sprint,
        jd_analysis=jd_analysis_dict(),
        company_context=valid_context(),
        company_context_status=CompanyContextStatus.PENDING_REVIEW,
        **opportunity_data(),
    )

    with pytest.raises(Http404):
        OpportunityService.update_company_context_review(
            user=other,
            sprint=other_sprint,
            opportunity_id=opportunity.pk,
            company_context_payload=valid_context(),
        )


@pytest.mark.django_db
def test_update_company_context_review_validates_payload_before_persistence():
    user, sprint, _profile = make_profile_confirmed_sprint()
    opportunity = Opportunity.objects.create(
        sprint=sprint,
        jd_analysis=jd_analysis_dict(),
        company_context=valid_context(),
        company_context_status=CompanyContextStatus.PENDING_REVIEW,
        **opportunity_data(),
    )

    with pytest.raises(ValueError):
        OpportunityService.update_company_context_review(
            user=user,
            sprint=sprint,
            opportunity_id=opportunity.pk,
            company_context_payload={
                "company_description": None,
                "products_or_services": [],
                "target_users": [],
                "business_model_clues": [],
                "product_terminology": [],
                "strategic_themes": [],
                "source_type": "paste",
                "source_url": None,
                "source_references": [],
                "uncertain_fields": [],
            },
        )

    opportunity.refresh_from_db()
    assert opportunity.company_context_status == CompanyContextStatus.PENDING_REVIEW
