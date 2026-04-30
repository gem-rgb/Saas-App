from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import JsonResponse

from .forms import ContactForm


def contact_view(request):
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    form = ContactForm(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            form.save()
            if is_ajax:
                return JsonResponse({
                    "status": "ok",
                    "message": "Thank you! Your message has been sent. We'll get back to you soon."
                })
            messages.success(request, "Thank you! Your message has been sent. We'll get back to you soon.")
            return redirect("contact")
        else:
            if is_ajax:
                return JsonResponse({
                    "status": "error",
                    "errors": form.errors
                }, status=400)
    return render(request, "contact/main.html", {"form": form})
