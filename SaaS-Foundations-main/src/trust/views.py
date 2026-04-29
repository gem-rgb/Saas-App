from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from trust.forms import IdentityVerificationForm, InterviewSessionForm, TaskerApplicationForm, TaskerDocumentForm
from trust.models import AIInterviewSession, IdentityVerification, TaskerApplication, TaskerDocument
from trust.services import evaluate_application, is_tasker_ready, run_ai_interview, score_application


@login_required
def application_dashboard_view(request):
    application, _ = TaskerApplication.objects.get_or_create(applicant=request.user)
    documents = application.documents.all()
    identity, _ = IdentityVerification.objects.get_or_create(application=application)
    interviews = application.interview_sessions.select_related("application").all()
    readiness = score_application(application)
    context = {
        "application": application,
        "documents": documents,
        "identity": identity,
        "interviews": interviews,
        "readiness": readiness,
        "is_ready": is_tasker_ready(application),
        "application_form": TaskerApplicationForm(instance=application),
        "document_form": TaskerDocumentForm(),
        "identity_form": IdentityVerificationForm(instance=identity) if identity else IdentityVerificationForm(),
        "interview_form": InterviewSessionForm(),
    }
    return render(request, "trust/dashboard.html", context)


@login_required
def application_submit_view(request):
    application, _ = TaskerApplication.objects.get_or_create(applicant=request.user)
    if request.method == "POST":
        app_form = TaskerApplicationForm(request.POST, instance=application)
        doc_form = TaskerDocumentForm(request.POST, request.FILES)
        identity = getattr(application, "identity_verification", None)
        identity_form = IdentityVerificationForm(request.POST, request.FILES, instance=identity) if identity else IdentityVerificationForm(request.POST, request.FILES)
        if app_form.is_valid() and doc_form.is_valid() and identity_form.is_valid():
            application = app_form.save(commit=False)
            application.applicant = request.user
            application.status = TaskerApplication.Status.SUBMITTED
            application.save()
            app_form.save_m2m()

            document = doc_form.save(commit=False)
            document.application = application
            document.save()

            identity = identity_form.save(commit=False)
            identity.application = application
            identity.save()

            result = evaluate_application(application)
            if request.POST.get("run_interview") == "1":
                session = run_ai_interview(application)
                application.interview_confidence = session.overall_score
                application.save(update_fields=["interview_confidence", "updated_at"])
                messages.success(request, f"AI interview completed with score {session.overall_score:.1f}.")

            messages.success(
                request,
                f"Application submitted. Trust score: {result['risk_result']['trust_score']:.1f}",
            )
            return redirect("trust:dashboard")
    else:
        app_form = TaskerApplicationForm(instance=application)
        doc_form = TaskerDocumentForm()
        identity = getattr(application, "identity_verification", None)
        identity_form = IdentityVerificationForm(instance=identity) if identity else IdentityVerificationForm()

    return render(
        request,
        "trust/application_form.html",
        {
            "application_form": app_form,
            "document_form": doc_form,
            "identity_form": identity_form,
            "application": application,
        },
    )


@login_required
def kyc_dashboard_view(request):
    application, _ = TaskerApplication.objects.get_or_create(applicant=request.user)
    identity, _ = IdentityVerification.objects.get_or_create(application=application)
    if request.method == "POST":
        form = IdentityVerificationForm(request.POST, request.FILES, instance=identity)
        if form.is_valid():
            identity = form.save(commit=False)
            identity.application = application
            identity.status = IdentityVerification.Status.UNDER_REVIEW
            identity.save()
            messages.success(request, "KYC data saved for review.")
            return redirect("trust:kyc_dashboard")
    else:
        form = IdentityVerificationForm(instance=identity)
    return render(
        request,
        "trust/kyc_dashboard.html",
        {
            "application": application,
            "identity": identity,
            "form": form,
        },
    )


@login_required
def interview_dashboard_view(request):
    application, _ = TaskerApplication.objects.get_or_create(applicant=request.user)
    if request.method == "POST":
        if request.POST.get("run_interview") == "1":
            session = run_ai_interview(application)
            messages.success(request, f"Interview completed: {session.recommendation}.")
            return redirect("trust:interview_dashboard")
    sessions = application.interview_sessions.all()
    return render(
        request,
        "trust/interview_dashboard.html",
        {
            "application": application,
            "sessions": sessions,
            "readiness": score_application(application),
        },
    )


@login_required
def application_review_view(request, pk):
    application = get_object_or_404(TaskerApplication, pk=pk)
    if not request.user.is_staff and not request.user.is_superuser:
        messages.error(request, "Only admins can review applications.")
        return redirect("trust:dashboard")

    if request.method == "POST":
        action = request.POST.get("action")
        application.reviewed_by = request.user
        application.reviewed_at = timezone.now()
        application.human_override = True
        if action == "approve":
            application.status = TaskerApplication.Status.APPROVED
            application.decision_reason = request.POST.get("decision_reason", "Approved by admin.")
        elif action == "reject":
            application.status = TaskerApplication.Status.REJECTED
            application.decision_reason = request.POST.get("decision_reason", "Rejected by admin.")
        else:
            application.status = TaskerApplication.Status.UNDER_REVIEW
        application.save()
        messages.success(request, f"Application {application.status}.")
    return redirect("trust:dashboard")
