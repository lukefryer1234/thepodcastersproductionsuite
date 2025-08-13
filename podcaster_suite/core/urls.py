from django.urls import path
from . import views
from django.contrib.auth import views as auth_views

urlpatterns = [
    path("", views.index, name="index"),
    path("register/", views.register, name="register"),
    path("login/", auth_views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("upload/", views.upload_file, name="upload_file"),
    path("de_um_audio/<int:audio_file_id>/", views.de_um_audio, name="de_um_audio"),
    path("generate_show_notes/<int:audio_file_id>/", views.generate_show_notes, name="generate_show_notes"),
    path("pricing/", views.pricing, name="pricing"),
    path("create-checkout-session/<str:price_id>/", views.create_checkout_session, name="create_checkout_session"),
    path("success/", views.success, name="success"),
    path("cancel/", views.cancel, name="cancel"),
    path("stripe_webhook/", views.stripe_webhook, name="stripe_webhook"),
]
