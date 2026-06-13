from apps.profiles.forms import CareerProfileForm


def test_profile_form_normalizes_lists_and_blank_values():
    form = CareerProfileForm(
        data={
            "full_name": "  ",
            "current_role": " Product Manager ",
            "current_company": "",
            "years_experience": "5",
            "industries": "SaaS\nSaaS, Fintech",
            "functional_areas": "Product, Growth",
            "skills": "Discovery\nRoadmapping",
            "tools": "Jira, Figma, jira",
            "education_summary": " MBA ",
            "career_summary": " Builds products ",
            "positioning_summary": " Product leader ",
        }
    )

    assert form.is_valid(), form.errors
    assert form.cleaned_data["full_name"] is None
    assert form.cleaned_data["industries"] == ["SaaS", "Fintech"]
    assert form.cleaned_data["tools"] == ["Jira", "Figma"]


def test_profile_form_rejects_sensitive_inference():
    form = CareerProfileForm(
        data={
            "full_name": "Alex",
            "current_role": "Product Manager",
            "current_company": "ExampleCo",
            "years_experience": "5",
            "industries": "SaaS",
            "functional_areas": "Product",
            "skills": "Discovery",
            "tools": "Jira",
            "education_summary": "",
            "career_summary": "Candidate gender appears female.",
            "positioning_summary": "",
        }
    )

    assert not form.is_valid()
    assert "career_summary" in form.errors


def test_profile_form_rejects_invalid_years():
    form = CareerProfileForm(data={"years_experience": "100"})

    assert not form.is_valid()
    assert "years_experience" in form.errors


def test_profile_form_rejects_direct_sensitive_value():
    form = CareerProfileForm(
        data={
            "full_name": "Alex",
            "current_role": "Product Manager",
            "current_company": "ExampleCo",
            "years_experience": "5",
            "industries": "SaaS",
            "functional_areas": "Product",
            "skills": "Discovery",
            "tools": "Jira",
            "education_summary": "",
            "career_summary": "Candidate appears female.",
            "positioning_summary": "",
        }
    )

    assert not form.is_valid()
    assert "career_summary" in form.errors
