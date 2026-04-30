import json
import hmac
import hashlib
from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.contrib.auth import get_user_model

import helpers.paystack_billing
from customers.models import Customer
from subscriptions.models import Subscription, UserSubscription

User = get_user_model()


@csrf_exempt
@require_POST
def paystack_webhook_view(request):
    """Handle Paystack webhook events for real-time subscription sync."""
    payload = request.body
    sig_header = request.META.get('HTTP_X_PAYSTACK_SIGNATURE', '')
    webhook_secret = getattr(settings, "PAYSTACK_SECRET_KEY", "")

    if webhook_secret:
        # Verify Paystack signature
        hash = hmac.new(webhook_secret.encode('utf-8'), payload, hashlib.sha512).hexdigest()
        if hash != sig_header:
            return HttpResponse(status=400)

    try:
        event = json.loads(payload)
    except json.JSONDecodeError:
        return HttpResponse(status=400)

    event_type = event.get('event', '')
    data = event.get('data', {})

    handlers = {
        'charge.success': handle_charge_success,
        'subscription.create': handle_subscription_create,
        'subscription.disable': handle_subscription_disable,
    }

    handler = handlers.get(event_type)
    if handler:
        try:
            handler(data)
        except Exception as e:
            print(f"Webhook handler error for {event_type}: {e}")
            return HttpResponse(status=500)

    return HttpResponse(status=200)


def handle_charge_success(data):
    """Process successful charge, which could be a subscription initialization."""
    customer_data = data.get('customer', {})
    customer_code = customer_data.get('customer_code')
    metadata = data.get('metadata', {})
    
    plan_code = metadata.get('plan_id')
    if not plan_code:
        # If it's a direct charge without a plan, ignore for subscriptions
        return

    try:
        user = User.objects.get(customer__paystack_id=customer_code)
    except User.DoesNotExist:
        return

    sub_obj = None
    if plan_code:
        try:
            sub_obj = Subscription.objects.get(subscriptionprice__paystack_id=plan_code)
        except Subscription.DoesNotExist:
            pass

    # The subscription code is not always in the charge event directly unless it's a renewal
    # but we can try to find it or we wait for subscription.create
    subscription_code = data.get('subscription_code')
    
    # We update or create assuming the transaction was successful
    defaults = {
        'subscription': sub_obj,
        'user_cancelled': False,
        'status': 'active',
    }
    
    if subscription_code:
        defaults['paystack_id'] = subscription_code

    UserSubscription.objects.update_or_create(
        user=user,
        defaults=defaults
    )


def handle_subscription_create(data):
    """Sync subscription creation."""
    subscription_code = data.get('subscription_code')
    customer_code = data.get('customer', {}).get('customer_code')
    plan_code = data.get('plan', {}).get('plan_code')
    
    if not subscription_code or not customer_code:
        return

    try:
        user = User.objects.get(customer__paystack_id=customer_code)
    except User.DoesNotExist:
        return

    sub_obj = None
    if plan_code:
        try:
            sub_obj = Subscription.objects.get(subscriptionprice__paystack_id=plan_code)
        except Subscription.DoesNotExist:
            pass

    UserSubscription.objects.update_or_create(
        user=user,
        defaults={
            'subscription': sub_obj,
            'paystack_id': subscription_code,
            'user_cancelled': False,
            'status': 'active',
        }
    )


def handle_subscription_disable(data):
    """Cancel subscription when disabled in Paystack."""
    subscription_code = data.get('subscription_code')
    if not subscription_code:
        return

    try:
        user_sub = UserSubscription.objects.get(paystack_id=subscription_code)
        user_sub.status = 'canceled'
        user_sub.active = False
        user_sub.user_cancelled = True
        user_sub.save()
    except UserSubscription.DoesNotExist:
        pass
