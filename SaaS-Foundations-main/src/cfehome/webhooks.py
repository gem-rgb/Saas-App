import json
import stripe
from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.contrib.auth import get_user_model

import helpers.billing
from customers.models import Customer
from subscriptions.models import Subscription, UserSubscription

User = get_user_model()


@csrf_exempt
@require_POST
def stripe_webhook_view(request):
    """Handle Stripe webhook events for real-time subscription sync."""
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE', '')
    webhook_secret = settings.STRIPE_WEBHOOK_SECRET

    if not webhook_secret:
        # No webhook secret configured — skip verification in dev
        try:
            event = json.loads(payload)
        except json.JSONDecodeError:
            return HttpResponse(status=400)
    else:
        try:
            event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
        except ValueError:
            return HttpResponse(status=400)
        except stripe.error.SignatureVerificationError:
            return HttpResponse(status=400)

    event_type = event.get('type', '')
    data = event.get('data', {}).get('object', {})

    handlers = {
        'checkout.session.completed': handle_checkout_completed,
        'invoice.payment_succeeded': handle_payment_succeeded,
        'invoice.payment_failed': handle_payment_failed,
        'customer.subscription.updated': handle_subscription_updated,
        'customer.subscription.deleted': handle_subscription_deleted,
    }

    handler = handlers.get(event_type)
    if handler:
        try:
            handler(data)
        except Exception as e:
            print(f"Webhook handler error for {event_type}: {e}")
            return HttpResponse(status=500)

    return HttpResponse(status=200)


def handle_checkout_completed(data):
    """Process completed checkout session."""
    customer_id = data.get('customer')
    subscription_id = data.get('subscription')
    if not subscription_id:
        return

    sub_response = helpers.billing.get_subscription(subscription_id, raw=True)
    sub_data = helpers.billing.serialize_subscription_data(sub_response)
    plan_id = sub_response.plan.id if sub_response.plan else None

    try:
        user = User.objects.get(customer__stripe_id=customer_id)
    except User.DoesNotExist:
        return

    sub_obj = None
    if plan_id:
        try:
            sub_obj = Subscription.objects.get(subscriptionprice__stripe_id=plan_id)
        except Subscription.DoesNotExist:
            pass

    UserSubscription.objects.update_or_create(
        user=user,
        defaults={
            'subscription': sub_obj,
            'stripe_id': subscription_id,
            'user_cancelled': False,
            **sub_data,
        }
    )


def handle_payment_succeeded(data):
    """Update subscription period on successful payment."""
    subscription_id = data.get('subscription')
    if not subscription_id:
        return

    try:
        user_sub = UserSubscription.objects.get(stripe_id=subscription_id)
    except UserSubscription.DoesNotExist:
        return

    sub_data = helpers.billing.get_subscription(subscription_id, raw=False)
    for k, v in sub_data.items():
        setattr(user_sub, k, v)
    user_sub.save()


def handle_payment_failed(data):
    """Mark subscription as past_due on failed payment."""
    subscription_id = data.get('subscription')
    if not subscription_id:
        return

    try:
        user_sub = UserSubscription.objects.get(stripe_id=subscription_id)
        user_sub.status = 'past_due'
        user_sub.save()
    except UserSubscription.DoesNotExist:
        pass


def handle_subscription_updated(data):
    """Sync subscription status changes."""
    subscription_id = data.get('id')
    if not subscription_id:
        return

    try:
        user_sub = UserSubscription.objects.get(stripe_id=subscription_id)
    except UserSubscription.DoesNotExist:
        return

    sub_data = helpers.billing.get_subscription(subscription_id, raw=False)
    for k, v in sub_data.items():
        setattr(user_sub, k, v)
    user_sub.save()


def handle_subscription_deleted(data):
    """Cancel subscription when deleted in Stripe."""
    subscription_id = data.get('id')
    if not subscription_id:
        return

    try:
        user_sub = UserSubscription.objects.get(stripe_id=subscription_id)
        user_sub.status = 'canceled'
        user_sub.active = False
        user_sub.user_cancelled = True
        user_sub.save()
    except UserSubscription.DoesNotExist:
        pass
