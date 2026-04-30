import requests
from django.conf import settings

PAYSTACK_SECRET_KEY = getattr(settings, "PAYSTACK_SECRET_KEY", "")
PAYSTACK_PUBLIC_KEY = getattr(settings, "PAYSTACK_PUBLIC_KEY", "")

BASE_URL = "https://api.paystack.co"

def get_headers():
    return {
        "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json",
    }

def initialize_transaction(email, amount_minor, reference=None, callback_url=None, metadata=None, plan=None):
    """
    Initialize a Paystack transaction.
    amount_minor is the amount in the smallest currency unit (e.g. Kobo for NGN, Cents for USD).
    """
    url = f"{BASE_URL}/transaction/initialize"
    
    payload = {
        "email": email,
        "amount": amount_minor,
    }
    
    if reference:
        payload["reference"] = reference
        
    if callback_url:
        payload["callback_url"] = callback_url
        
    if metadata:
        payload["metadata"] = metadata
        
    if plan:
        payload["plan"] = plan
        
    response = requests.post(url, json=payload, headers=get_headers())
    response.raise_for_status()
    return response.json()


def verify_transaction(reference):
    """
    Verify a Paystack transaction by its reference.
    """
    url = f"{BASE_URL}/transaction/verify/{reference}"
    response = requests.get(url, headers=get_headers())
    response.raise_for_status()
    return response.json()

def create_customer(email, first_name="", last_name="", metadata=None):
    """
    Create a Paystack customer.
    """
    url = f"{BASE_URL}/customer"
    payload = {
        "email": email,
        "first_name": first_name,
        "last_name": last_name,
    }
    if metadata:
        payload["metadata"] = metadata
        
    response = requests.post(url, json=payload, headers=get_headers())
    response.raise_for_status()
    data = response.json()
    return data.get("data", {}).get("customer_code")

def create_plan(name, amount_minor, interval, description=None):
    """
    Create a Paystack Plan.
    interval can be: hourly, daily, weekly, monthly, biannually, annually.
    amount_minor is in kobo/cents.
    """
    url = f"{BASE_URL}/plan"
    payload = {
        "name": name,
        "amount": amount_minor,
        "interval": interval,
    }
    if description:
        payload["description"] = description
        
    response = requests.post(url, json=payload, headers=get_headers())
    response.raise_for_status()
    data = response.json()
    return data.get("data", {}).get("plan_code")

def cancel_subscription(subscription_code, token):
    """
    Disable a Paystack subscription.
    Requires the subscription_code and the email token.
    """
    url = f"{BASE_URL}/subscription/disable"
    payload = {
        "code": subscription_code,
        "token": token
    }
    response = requests.post(url, json=payload, headers=get_headers())
    response.raise_for_status()
    return response.json()
