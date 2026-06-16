import pytest

from ai.client import MockAIClient
from ai.services import AIPrepKitArtifactError, EvidraAIService

BASE_PAYLOAD = {
    "opportunity_context": {"role_title": "Product Manager", "company_name": "Example"},
    "role_pack": {},
    "matches": [{"id": 1, "competency_key": "product_strategy"}],
    "stories": [{"id": 1, "evidence_ids": [1]}],
    "approved_evidence": [{"id": 1, "title": "Approved evidence"}],
    "preview": {"id": 1},
}


def test_generate_prepkit_analysis_uses_structured_schema():
    client = MockAIClient()

    analysis = EvidraAIService(client=client).generate_prepkit_analysis(**BASE_PAYLOAD)

    assert analysis.role_briefing_points[0].evidence_ids == [1]


def test_generate_prepkit_artifact_retries_once_for_structural_failure():
    valid_client = MockAIClient()
    valid = valid_client.generate_prepkit_artifact(**BASE_PAYLOAD, analysis={})
    client = MockAIClient(responses=[{"role_briefing": {}}, valid])

    artifact = EvidraAIService(client=client).generate_prepkit_artifact(
        **BASE_PAYLOAD, analysis={}
    )

    assert artifact.role_briefing.role_title == "Product Manager"
    assert len(client.calls) == 2


def test_generate_prepkit_artifact_fails_after_retry():
    client = MockAIClient(responses=[{"role_briefing": {}}, {"role_briefing": {}}])

    with pytest.raises(AIPrepKitArtifactError):
        EvidraAIService(client=client).generate_prepkit_artifact(**BASE_PAYLOAD, analysis={})
