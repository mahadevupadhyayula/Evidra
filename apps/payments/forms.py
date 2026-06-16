from django import forms


class PaymentStartForm(forms.Form):
    """CSRF-protected action form; server-side services load Sprint and amount."""


class PaymentRetryForm(forms.Form):
    """CSRF-protected retry form; browser-submitted payment IDs are not trusted."""
