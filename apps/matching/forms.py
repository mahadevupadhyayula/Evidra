from django import forms


class StoryMatchOverrideForm(forms.Form):
    selected_story_id = forms.IntegerField(required=False, min_value=1)
