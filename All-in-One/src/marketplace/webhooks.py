import json
import hashlib
import hmac
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from marketplace.models import TaskPayment, TaskStatusEvent

@csrf_exempt
def paystack_webhook_view(request):
    """
    Handle Paystack webhooks.
    https://paystack.com/docs/payments/webhooks/
    """
    if request.method != "POST":
        return HttpResponse(status=405)
        
    secret = getattr(settings, "PAYSTACK_SECRET_KEY", "")
    
    # Verify Paystack signature
    paystack_signature = request.headers.get("x-paystack-signature")
    if not paystack_signature:
        return HttpResponse(status=400)
        
    hash = hmac.new(secret.encode("utf-8"), request.body, hashlib.sha512).hexdigest()
    if hash != paystack_signature:
        return HttpResponse(status=400)
        
    try:
        event = json.loads(request.body)
    except json.JSONDecodeError:
        return HttpResponse(status=400)
        
    event_name = event.get("event")
    data = event.get("data", {})
    
    if event_name == "charge.success":
        reference = data.get("reference")
        try:
            payment = TaskPayment.objects.get(provider_reference=reference)
            if payment.status == TaskPayment.Status.PENDING:
                payment.status = TaskPayment.Status.AUTHORIZED
                payment.save()
                
                # Update task status to posted if it's still in draft
                task = payment.task
                if task.status == "draft":
                    task.status = task.Status.OPEN
                    task.save()
                    TaskStatusEvent.objects.create(
                        task=task,
                        actor=task.student,
                        previous_status=task.Status.DRAFT,
                        new_status=task.Status.OPEN,
                        actor_role="system",
                        note="Payment authorized via Paystack",
                    )
        except TaskPayment.DoesNotExist:
            pass
            
    return HttpResponse(status=200)
