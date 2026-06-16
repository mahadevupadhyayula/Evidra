from django.urls import path

from apps.payments import views

app_name = "payments"

urlpatterns = [
    path("checkout/", views.payment_checkout, name="checkout"),
    path("status/", views.payment_status, name="status"),
    path("status/poll/", views.payment_status_poll, name="status_poll"),
    path("retry/", views.payment_retry, name="retry"),
    path("webhook/razorpay/", views.razorpay_webhook, name="razorpay_webhook"),
]
