import pytest

from ai.client import AIClientError, MockAIClient
from ai.services import AIJDAnalysisError, EvidraAIService
from tests.opportunities.helpers import jd_analysis_dict, jd_text


def test_analyze_jd_retries_once_for_structural_failure():
    valid = jd_analysis_dict()
    client = MockAIClient(responses=[{"summary": "Invalid only"}, valid])

    analysis = EvidraAIService(client=client).analyze_jd(
        job_description=jd_text(),
        role_title="Senior Product Manager",
        role_family="PRODUCT_MANAGEMENT",
        target_seniority="Senior",
        role_pack={"key": "PRODUCT_MANAGEMENT"},
    )

    assert analysis.summary == valid["summary"]
    assert len(client.calls) == 2
    assert client.calls[1]["retry_context"]


def test_analyze_jd_raises_after_two_failures():
    client = MockAIClient(responses=[AIClientError("down"), AIClientError("down")])

    with pytest.raises(AIJDAnalysisError):
        EvidraAIService(client=client).analyze_jd(
            job_description=jd_text(),
            role_title="Senior Product Manager",
            role_family="PRODUCT_MANAGEMENT",
            target_seniority="Senior",
            role_pack={"key": "PRODUCT_MANAGEMENT"},
        )

    assert len(client.calls) == 2


def test_analyze_jd_drops_unsupported_source_excerpt():
    data = jd_analysis_dict()
    data["competencies"][0]["source_excerpt"] = "not in the jd"
    client = MockAIClient(responses=[data])

    analysis = EvidraAIService(client=client).analyze_jd(
        job_description=jd_text(),
        role_title="Senior Product Manager",
        role_family="PRODUCT_MANAGEMENT",
        target_seniority="Senior",
        role_pack={"key": "PRODUCT_MANAGEMENT"},
    )

    assert analysis.competencies[0].source_excerpt is None
