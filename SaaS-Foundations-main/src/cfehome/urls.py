"""
URL configuration for cfehome project.
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from auth import views as auth_views
from checkouts import views as checkout_views
from landing import views as landing_views
from subscriptions import views as subscriptions_views
from contact import views as contact_views
from analytics import views as analytics_views
from cfehome import webhooks

from .views import (
    home_view, 
    about_view, 
    pw_protected_view,
    user_only_view,
    staff_only_view,
    services_view,
)

urlpatterns = [
    path("", landing_views.landing_dashboard_page_view, name='home'),
    path("checkout/sub-price/<int:price_id>/", 
            checkout_views.product_price_redirect_view,
            name='sub-price-checkout'
            ),
    path("checkout/start/", 
            checkout_views.checkout_redirect_view,
            name='stripe-checkout-start'
            ),
    path("checkout/success/", 
            checkout_views.checkout_finalize_view,
            name='stripe-checkout-end'
            ),
    path("pricing/", subscriptions_views.subscription_price_view, name='pricing'),
    path("pricing/<str:interval>/", subscriptions_views.subscription_price_view, name='pricing_interval'),
    path("about/", about_view, name='about'),
    path("contact/", contact_views.contact_view, name='contact'),
    path("services/", services_view, name='services'),
    path("hello-world/", home_view),
    path("hello-world.html", home_view),
    # Platform portals
    path("portal/", include("dashboard.urls")),
    path("marketplace/", include("marketplace.urls")),
    path("trust/", include("trust.urls")),
    path("operations/", include("operations.urls")),
    # Account & Billing
    path('accounts/billing/', subscriptions_views.user_subscription_view, name='user_subscription'),
    path('accounts/billing/cancel', subscriptions_views.user_subscription_cancel_view, name='user_subscription_cancel'),
    path('accounts/', include('allauth.urls')),
    # Profiles
    path('profiles/', include('profiles.urls')),
    # Assignments
    path('assignments/', include('assignments.urls')),
    # Analytics
    path('analytics/', analytics_views.analytics_dashboard_view, name='analytics_dashboard'),
    # API
    path('api/', include('api.urls')),
    # Webhooks
    path('webhooks/stripe/', webhooks.stripe_webhook_view, name='stripe-webhook'),
    # Protected
    path('protected/user-only/', user_only_view),
    path('protected/staff-only/', staff_only_view),
    path('protected/', pw_protected_view),
    # Admin
    path("admin/", admin.site.urls),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
