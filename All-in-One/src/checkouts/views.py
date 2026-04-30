import helpers.paystack_billing
from django.shortcuts import render, redirect
from django.urls import reverse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.conf import settings
from django.http import HttpResponseBadRequest

from subscriptions.models import SubscriptionPrice, Subscription, UserSubscription

User = get_user_model()

BASE_URL = settings.BASE_URL
# Create your views here.
def product_price_redirect_view(request, price_id=None, *args, **kwargs):
    request.session['checkout_subscription_price_id'] = price_id
    return redirect("stripe-checkout-start")


@login_required
def checkout_redirect_view(request):
    checkout_subscription_price_id = request.session.get("checkout_subscription_price_id")
    try:
        obj = SubscriptionPrice.objects.get(id=checkout_subscription_price_id)
    except:
        obj = None
    if checkout_subscription_price_id is None or obj is None:
        return redirect("pricing")
    # Generate a unique reference
    import uuid
    reference = str(uuid.uuid4())
    success_url_path = reverse("stripe-checkout-end")
    success_url = f"{BASE_URL}{success_url_path}"
    
    try:
        response_data = helpers.paystack_billing.initialize_transaction(
            email=request.user.email,
            amount_minor=int(obj.price * 100),
            reference=reference,
            callback_url=success_url,
            plan=obj.paystack_id,
            metadata={
                "customer_id": request.user.customer.paystack_id,
                "plan_id": obj.paystack_id,
                "user_id": request.user.id
            }
        )
        url = response_data.get("data", {}).get("authorization_url")
        if not url:
            return redirect("pricing")
    except Exception as e:
        print(f"Paystack Init Error: {e}")
        return redirect("pricing")
        
    return redirect(url)


def checkout_finalize_view(request):
    reference = request.GET.get('reference')
    if not reference:
        return redirect("pricing")
        
    try:
        verify_data = helpers.paystack_billing.verify_transaction(reference)
        status = verify_data.get("data", {}).get("status")
        if status != "success":
            return HttpResponseBadRequest("Transaction was not successful.")
            
        metadata = verify_data.get("data", {}).get("metadata", {})
        plan_id = metadata.get('plan_id')
        customer_id = metadata.get('customer_id')
        
        # Paystack doesn't send sub ID immediately in verify, it sends it via webhook usually.
        # We will create an inactive sub or try to get it.
        sub_paystack_id = verify_data.get("data", {}).get("authorization", {}).get("authorization_code")
        
    except Exception as e:
        print(f"Paystack Verify Error: {e}")
        return HttpResponseBadRequest("Could not verify transaction.")

    try:
        sub_obj = Subscription.objects.get(subscriptionprice__paystack_id=plan_id)
    except:
        sub_obj = None
    try:
        user_obj = User.objects.get(customer__paystack_id=customer_id)
    except:
        user_obj = None

    _user_sub_exists = False
    updated_sub_options = {
        "subscription": sub_obj,
        "paystack_id": sub_paystack_id, # Can be authorization code for now
        "user_cancelled": False,
        "status": "active",
    }
    try:
        _user_sub_obj = UserSubscription.objects.get(user=user_obj)
        _user_sub_exists = True
    except UserSubscription.DoesNotExist:
        _user_sub_obj = UserSubscription.objects.create(
            user=user_obj, 
            **updated_sub_options
        )
    except:
        _user_sub_obj = None
    if None in [sub_obj, user_obj, _user_sub_obj]:
        return HttpResponseBadRequest("There was an error with your account, please contact us.")
    if _user_sub_exists:
        # cancel old sub
        old_paystack_id = _user_sub_obj.paystack_id
        same_paystack_id = sub_paystack_id == old_paystack_id
        if old_paystack_id is not None and not same_paystack_id:
            try:
                # We would need the email token to cancel in Paystack API
                pass
            except:
                pass
        # assign new sub
        for k, v in updated_sub_options.items():
            setattr(_user_sub_obj, k, v)
        _user_sub_obj.save()
        messages.success(request, "Success! Thank you for joining.")
        return redirect(_user_sub_obj.get_absolute_url())
    context = {}
    return render(request, "checkout/success.html", context)