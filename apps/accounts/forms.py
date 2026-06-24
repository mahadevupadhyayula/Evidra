from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm


class EmailAuthenticationForm(AuthenticationForm):
    username = forms.CharField(
        label="Email",
        widget=forms.TextInput(attrs={"placeholder": "name@company.com"}),
    )
    password = forms.CharField(
        label="Password",
        strip=False,
        widget=forms.PasswordInput(attrs={"placeholder": "Enter your password"}),
    )


class EmailSignupForm(UserCreationForm):
    full_name = forms.CharField(label="Full Name", max_length=150)
    email = forms.EmailField(label="Email", max_length=254)

    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ("full_name", "email")

    def clean_email(self) -> str:
        email = self.cleaned_data["email"].strip().lower()
        User = get_user_model()
        if (
            User.objects.filter(email__iexact=email).exists()
            or User.objects.filter(username__iexact=email).exists()
        ):
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def save(self, commit: bool = True):
        user = super().save(commit=False)
        user.first_name = self.cleaned_data["full_name"].strip()
        user.email = self.cleaned_data["email"]
        user.username = self.cleaned_data["email"]
        if commit:
            user.save()
        return user
