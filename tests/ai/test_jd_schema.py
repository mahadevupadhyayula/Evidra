import pytest
from pydantic import ValidationError

from ai.schemas.jd import JDAnalysis
from tests.opportunities.helpers import jd_analysis_dict


def test_jd_analysis_accepts_valid_schema():
    analysis = JDAnalysis.model_validate(jd_analysis_dict())

    assert analysis.summary.startswith("The role")
    assert analysis.competencies[0].name == "Product strategy"


def test_jd_analysis_rejects_extra_fields():
    data = jd_analysis_dict()
    data["unexpected"] = "nope"

    with pytest.raises(ValidationError):
        JDAnalysis.model_validate(data)


def test_jd_analysis_requires_useful_content():
    data = jd_analysis_dict()
    data["competencies"] = []
    data["skills"] = []
    data["seniority_expectations"] = []

    with pytest.raises(ValidationError):
        JDAnalysis.model_validate(data)
