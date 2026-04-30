from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from agents.interview_agent import infer_interview_focus
from auth.models import UserRole
from auth.permissions import portal_url_for_user, require_any_role, require_tasker
from trust.forms import IdentityVerificationForm, InterviewSessionForm, TaskerApplicationForm, TaskerDocumentForm, TaskerKYCForm
from trust.models import AIInterviewSession, IdentityVerification, InteractiveInterviewSession, TaskerApplication, TaskerDocument
from trust.services import evaluate_application, is_tasker_ready, run_ai_interview, score_application
from marketplace.permissions import can_receive_work


def _interview_focus_context(application):
    focus = infer_interview_focus(application)
    field = focus.get("field", "general_knowledge")
    try:
        focus["field_label"] = InteractiveInterviewSession.InterviewField(field).label
    except ValueError:
        focus["field_label"] = field.replace("_", " ").title()
    return focus


def _tasker_trust_context(application, identity=None):
    if identity is None:
        identity, _ = IdentityVerification.objects.get_or_create(application=application)
    return {
        "application": application,
        "identity": identity,
        "selected_competencies": application.competency_areas.all(),
        "competency_count": application.competency_areas.count(),
        "interview_focus": _interview_focus_context(application),
        "onboarding_url": reverse("trust:onboarding"),
        "portal_url": portal_url_for_user(application.applicant),
    }


@require_tasker
@login_required
def application_dashboard_view(request):
    application, _ = TaskerApplication.objects.get_or_create(applicant=request.user)
    documents = application.documents.all()
    identity, _ = IdentityVerification.objects.get_or_create(application=application)
    tasker_profile = getattr(request.user, "tasker_profile", None)
    tasker_portal_ready = can_receive_work(tasker_profile)
    interviews = application.interview_sessions.select_related("application").all()
    readiness = score_application(application)
    context = {
        "application": application,
        "documents": documents,
        "identity": identity,
        "interviews": interviews,
        "readiness": readiness,
        "is_ready": is_tasker_ready(application),
        "tasker_portal_ready": can_receive_work(getattr(request.user, "tasker_profile", None)),
        "selected_competencies": application.competency_areas.all(),
        "competency_count": application.competency_areas.count(),
        "interview_focus": _interview_focus_context(application),
        "onboarding_url": reverse("trust:onboarding"),
        "tasker_profile_url": reverse("assignments:tasker_profile"),
        "portal_url": portal_url_for_user(request.user),
        "application_form": TaskerApplicationForm(instance=application),
        "document_form": TaskerDocumentForm(),
        "identity_form": IdentityVerificationForm(instance=identity) if identity else IdentityVerificationForm(),
        "interview_form": InterviewSessionForm(),
    }
    return render(request, "trust/dashboard.html", context)


@require_tasker
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
                application.status = TaskerApplication.Status.INTERVIEW_PENDING
                application.interview_confidence = session.overall_score
                application.save(update_fields=["status", "interview_confidence", "updated_at"])
                messages.success(request, f"AI interview completed with score {session.overall_score:.1f}.")

                messages.success(
                    request,
                    f"Application submitted. Trust score: {result['risk_result']['trust_score']:.1f}",
                )
                return redirect("trust:onboarding")

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


@require_tasker
@login_required
def kyc_dashboard_view(request):
    application, _ = TaskerApplication.objects.get_or_create(applicant=request.user)
    identity, _ = IdentityVerification.objects.get_or_create(application=application)
    if request.method == "POST":
        form = TaskerKYCForm(request.POST, request.FILES, instance=identity)
        if form.is_valid():
            identity = form.save(commit=False)
            identity.application = application
            identity.status = IdentityVerification.Status.UNDER_REVIEW
            identity.save()
            messages.success(request, "KYC data saved for review.")
            return redirect("trust:kyc_dashboard")
    else:
        form = TaskerKYCForm(instance=identity)
    return render(
        request,
        "trust/kyc_dashboard.html",
        {
            "application": application,
            "identity": identity,
            "form": form,
        },
    )


@require_tasker
@login_required
def onboarding_view(request):
    application, _ = TaskerApplication.objects.get_or_create(applicant=request.user)
    tasker_profile = getattr(request.user, "tasker_profile", None)
    tasker_portal_ready = can_receive_work(tasker_profile)
    if application.status == TaskerApplication.Status.APPROVED and tasker_portal_ready:
        return redirect(portal_url_for_user(request.user))
    if request.method == "POST" and application.status == TaskerApplication.Status.APPROVED and not tasker_portal_ready:
        messages.info(request, "Use the tasker profile editor to restore portal access.")
        return redirect("assignments:tasker_profile")

    identity, _ = IdentityVerification.objects.get_or_create(application=application)

    if request.method == "POST":
        application_form = TaskerApplicationForm(request.POST, instance=application)
        kyc_form = TaskerKYCForm(request.POST, request.FILES, instance=identity)
        if application_form.is_valid() and kyc_form.is_valid():
            selected_competencies = application_form.cleaned_data.get("competency_areas")
            if not selected_competencies:
                application_form.add_error("competency_areas", "Select at least one competency area to continue.")
            else:
                application = application_form.save(commit=False)
                application.applicant = request.user
                application.status = TaskerApplication.Status.UNDER_REVIEW
                application.decision_reason = "Submitted from onboarding and waiting for manager approval."
                application.save()
                application_form.save_m2m()

                identity = kyc_form.save(commit=False)
                identity.application = application
                identity.status = IdentityVerification.Status.UNDER_REVIEW
                identity.save()

                evaluate_application(application)
                messages.success(request, "Onboarding submitted. Your manager will review it shortly.")
                return redirect("trust:onboarding")
    else:
        application_form = TaskerApplicationForm(instance=application)
        kyc_form = TaskerKYCForm(instance=identity)

    return render(
        request,
        "trust/onboarding.html",
        {
        "application": application,
        "identity": identity,
        "application_form": application_form,
        "kyc_form": kyc_form,
        "interviews": application.interview_sessions.all(),
        "readiness": score_application(application),
        "selected_competencies": application.competency_areas.all(),
        "competency_count": application.competency_areas.count(),
        "interview_focus": _interview_focus_context(application),
        "tasker_portal_ready": tasker_portal_ready,
        "portal_url": (
            portal_url_for_user(request.user)
            if tasker_portal_ready
            else reverse("assignments:tasker_profile")
                if application.status == TaskerApplication.Status.APPROVED
                else reverse("trust:dashboard")
            ),
        },
    )


@require_tasker
@login_required
def interview_dashboard_view(request):
    application, _ = TaskerApplication.objects.get_or_create(applicant=request.user)
    if request.method == "POST":
        if request.POST.get("run_interview") == "1":
            session = run_ai_interview(application)
            application.status = TaskerApplication.Status.INTERVIEW_PENDING
            application.save(update_fields=["status", "updated_at"])
            messages.success(request, f"Interview completed: {session.recommendation}.")
            return redirect("trust:onboarding")
    sessions = application.interview_sessions.all()
    return render(
        request,
        "trust/interview_dashboard.html",
        {
            "application": application,
            "sessions": sessions,
            "readiness": score_application(application),
            "onboarding_url": reverse("trust:onboarding"),
            "interview_focus": _interview_focus_context(application),
        },
    )


@require_any_role(UserRole.RoleType.MANAGER, UserRole.RoleType.ADMIN)
@login_required
def application_review_view(request, pk):
    application = get_object_or_404(TaskerApplication, pk=pk)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "approve":
            identity = getattr(application, "identity_verification", None)
            if identity is None or identity.status != IdentityVerification.Status.APPROVED:
                application.status = TaskerApplication.Status.UNDER_REVIEW
                application.decision_reason = "KYC must be approved before manager approval."
                application.save(update_fields=["status", "decision_reason", "updated_at"])
                messages.error(request, "Approve KYC before approving the tasker application.")
                return redirect("trust:dashboard")
            application.reviewed_by = request.user
            application.reviewed_at = timezone.now()
            application.human_override = True
            application.status = TaskerApplication.Status.APPROVED
            application.decision_reason = request.POST.get("decision_reason", "Approved by admin.")
        elif action == "reject":
            application.reviewed_by = request.user
            application.reviewed_at = timezone.now()
            application.human_override = True
            application.status = TaskerApplication.Status.REJECTED
            application.decision_reason = request.POST.get("decision_reason", "Rejected by admin.")
        else:
            application.status = TaskerApplication.Status.UNDER_REVIEW
        application.save()
        messages.success(request, f"Application {application.status}.")
    return redirect("trust:dashboard")
