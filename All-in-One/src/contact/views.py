from django.shortcuts import render, redirect
from django.contrib import messages

from .forms import ContactForm


def contact_view(request):
    form = ContactForm(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            form.save()
            messages.success(request, "Thank you! Your message has been sent. We'll get back to you soon.")
            return redirect("contact")
    return render(request, "contact/main.html", {"form": form})
