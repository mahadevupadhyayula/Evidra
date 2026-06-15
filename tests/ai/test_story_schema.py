import pytest
from pydantic import ValidationError

from ai.schemas.stories import GeneratedStorySet, StoryScoreSet
from tests.stories.helpers import generated_story, story_score


def test_generated_story_schema_accepts_valid_payload():
    payload = {"stories": [generated_story(1)]}

    stories = GeneratedStorySet.model_validate(payload)

    assert stories.stories[0].evidence_ids == [1]
    assert stories.stories[0].competency_tags == ["Execution"]


def test_generated_story_schema_rejects_extra_fields():
    payload = {"stories": [{**generated_story(1), "unexpected": "no"}]}

    with pytest.raises(ValidationError):
        GeneratedStorySet.model_validate(payload)


def test_story_score_schema_rejects_out_of_range_score():
    payload = {"scores": [{**story_score(), "impact_score": 101}]}

    with pytest.raises(ValidationError):
        StoryScoreSet.model_validate(payload)
