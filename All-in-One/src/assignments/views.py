from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.generic import ListView, DetailView, CreateView, UpdateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.db.models import Q
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_POST

from auth.models import UserRole
from auth.permissions import get_user_role, require_any_role, require_student, require_tasker
from agents.verification_service import run_assignment_verification
from agents.rubric_utils import normalize_rubric
from trust.models import TaskerApplication
from .models import (
    Assignment,
    AssignmentFile,
    AssignmentSubmission,
    AssignmentVerification,
    AssignmentVerificationCheck,
    TaskerProfile,
)
from .forms import AssignmentForm, AssignmentFileForm, TaskerProfileForm, AssignmentSubmissionForm
from analytics.ml_engine import match_assignment_to_taskers


def _assignment_queryset_for_user(user):
    user_role = get_user_role(user)
    role_type = user_role.role_type if user_role else UserRole.RoleType.STUDENT

    queryset = Assignment.objects.all()
    if role_type == UserRole.RoleType.TASKER:
        tasker_profile = getattr(user, "tasker_profile", None)
        if tasker_profile is None:
            return queryset.none()
        return queryset.filter(assigned_to=tasker_profile)

    if role_type in (UserRole.RoleType.MANAGER, UserRole.RoleType.ADMIN):
        return queryset

    return queryset.filter(creator=user)


def _assignment_verification_rubric(assignment):
    return normalize_rubric(assignment.verification_rubric if isinstance(assignment.verification_rubric, dict) else {})


def _assignment_submission_verification_payload(submission):
    verification = getattr(submission, "verification", None)
    if verification is None:
        return {}

    verification_results = verification.verification_results if isinstance(verification.verification_results, dict) else {}
    checks = []
    criteria = []
    seen_criteria = set()

    for check in verification.checks.all():
        details = check.details if isinstance(check.details, dict) else {}
        raw_criteria = details.get("criteria")
        if isinstance(raw_criteria, list):
            for criterion in raw_criteria:
                if not isinstance(criterion, dict):
                    continue
                criterion_key = (
                    criterion.get("name"),
                    tuple(criterion.get("required_terms") or []),
                )
                if criterion_key in seen_criteria:
                    continue
                seen_criteria.add(criterion_key)
                criteria.append(criterion)
        checks.append(
            {
                "check_type": check.check_type,
                "score": check.score,
                "details": details,
                "passed": check.passed,
            }
        )

    payload = dict(verification_results)
    payload["overall_score"] = payload.get("overall_score", verification.overall_score)
    payload["passed"] = payload.get("passed", verification.passed)
    payload["summary"] = payload.get("summary") or f"AI verification completed with a score of {verification.overall_score:.1f}/100."
    payload["source"] = payload.get("source") or "gemini"
    payload["grading_style"] = payload.get("grading_style") or ""
    payload["minimum_score"] = payload.get("minimum_score") or 70
    payload["checks"] = checks
    payload["criteria"] = criteria
    return payload


def _enrich_submission_with_verification(submission):
    submission.ai_verification = _assignment_submission_verification_payload(submission)
    return submission


# ============ Dashboard Views ============

@login_required
def assignment_dashboard(request):
    """Main dashboard for assignment management"""
    user = request.user

    user_role = get_user_role(user)
    is_tasker = user_role and user_role.role_type == UserRole.RoleType.TASKER and hasattr(user, "tasker_profile")
    
    if is_tasker:
        # Tasker view
        tasker = user.tasker_profile
        assigned_assignments = Assignment.objects.filter(assigned_to=tasker)
        pending_count = assigned_assignments.filter(status='in_progress').count()
        completed_count = assigned_assignments.filter(status='completed').count()
        
        context = {
            'is_tasker': True,
            'pending_count': pending_count,
            'completed_count': completed_count,
            'recent_assignments': assigned_assignments[:5],
            'tasker_profile': tasker,
        }
    else:
        # Assignment creator view
        created_assignments = Assignment.objects.filter(creator=user)
        posted_count = created_assignments.filter(status='posted').count()
        in_progress_count = created_assignments.filter(status='in_progress').count()
        completed_count = created_assignments.filter(status='completed').count()
        
        context = {
            'is_tasker': False,
            'posted_count': posted_count,
            'in_progress_count': in_progress_count,
            'completed_count': completed_count,
            'recent_assignments': created_assignments[:5],
        }
    
    return render(request, 'assignments/dashboard.html', context)


# ============ Assignment Management Views ============

class AssignmentListView(LoginRequiredMixin, ListView):
    """List all assignments (with filters for creators vs taskers)"""
    model = Assignment
    template_name = 'assignments/assignment_list.html'
    context_object_name = 'assignments'
    paginate_by = 20

    def get_queryset(self):
        queryset = _assignment_queryset_for_user(self.request.user)
        
        # Filter by status
        status = self.request.GET.get('status')
        if status:
            queryset = queryset.filter(status=status)
        
        # Filter by priority
        priority = self.request.GET.get('priority')
        if priority:
            queryset = queryset.filter(priority=priority)
        
        # Search
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) | Q(description__icontains=search)
            )
        
        return queryset.order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['status_choices'] = Assignment.STATUS_CHOICES
        context['priority_choices'] = Assignment.PRIORITY_CHOICES
        return context


class AssignmentDetailView(LoginRequiredMixin, DetailView):
    """View assignment details"""
    model = Assignment
    template_name = 'assignments/assignment_detail.html'
    context_object_name = 'assignment'

    def get_queryset(self):
        return _assignment_queryset_for_user(self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        assignment = self.get_object()
        context['files'] = assignment.files.all()
        context['assignment_verification_rubric'] = _assignment_verification_rubric(assignment)
        context['submissions'] = [
            _enrich_submission_with_verification(submission)
            for submission in assignment.submissions.select_related("tasker__user", "verification").prefetch_related("verification__checks").all()
        ]
        context['is_creator'] = assignment.creator == self.request.user
        context['is_assigned_tasker'] = (
            hasattr(self.request.user, 'tasker_profile') and 
            assignment.assigned_to == self.request.user.tasker_profile
        )
        return context


@method_decorator(require_student, name="dispatch")
class AssignmentCreateView(LoginRequiredMixin, CreateView):
    """Create a new assignment"""
    model = Assignment
    form_class = AssignmentForm
    template_name = 'assignments/assignment_form.html'
    success_url = reverse_lazy('assignments:assignment_list')

    def form_valid(self, form):
        form.instance.creator = self.request.user
        form.instance.status = 'draft'
        return super().form_valid(form)


class AssignmentUpdateView(LoginRequiredMixin, UpdateView):
    """Update an assignment"""
    model = Assignment
    form_class = AssignmentForm
    template_name = 'assignments/assignment_form.html'
    success_url = reverse_lazy('assignments:assignment_list')

    def get_queryset(self):
        return Assignment.objects.filter(creator=self.request.user)


@login_required
@require_POST
def publish_assignment(request, pk):
    """Publish a draft assignment and use ML to match with taskers"""
    assignment = get_object_or_404(Assignment, pk=pk, creator=request.user)
    
    if assignment.status != 'draft':
        return redirect('assignments:assignment_detail', pk=pk)
    
    assignment.status = 'posted'
    assignment.save()
    
    # Use ML engine to find matching taskers
    matches = match_assignment_to_taskers(assignment)
    
    return redirect('assignments:assignment_detail', pk=pk)


@login_required
@require_POST
def assign_to_tasker(request, assignment_id, tasker_id):
    """Manually assign an assignment to a specific tasker"""
    assignment = get_object_or_404(Assignment, pk=assignment_id, creator=request.user)
    tasker = get_object_or_404(TaskerProfile, pk=tasker_id)
    
    # Get ML match score
    matches = match_assignment_to_taskers(assignment)
    match_score = next((m['score'] for m in matches if m['tasker'].id == tasker.id), 0)
    
    assignment.assign_to_tasker(tasker)
    assignment.ml_match_score = match_score
    assignment.save()
    
    return redirect('assignments:assignment_detail', pk=assignment_id)


# ============ File Management Views ============

@login_required
def upload_assignment_file(request, assignment_id):
    """Upload a file to an assignment"""
    assignment = get_object_or_404(Assignment, pk=assignment_id, creator=request.user)
    
    if request.method == 'POST':
        form = AssignmentFileForm(request.POST, request.FILES)
        if form.is_valid():
            file_obj = form.save(commit=False)
            file_obj.assignment = assignment
            file_obj.uploaded_by = request.user
            file_obj.save()
            return redirect('assignments:assignment_detail', pk=assignment_id)
    else:
        form = AssignmentFileForm()
    
    return render(request, 'assignments/upload_file.html', {
        'form': form,
        'assignment': assignment
    })


# ============ Tasker Profile Views ============

@require_tasker
@login_required
def tasker_profile_view(request):
    """View or create tasker profile"""
    tasker, created = TaskerProfile.objects.get_or_create(user=request.user)
    application = getattr(request.user, "tasker_application", None)
    if application is None or application.status != TaskerApplication.Status.APPROVED:
        messages.info(request, "Complete onboarding in the Trust Hub before editing the tasker portal.")
        return redirect("trust:onboarding")
    
    if request.method == 'POST':
        form = TaskerProfileForm(request.POST, instance=tasker)
        if form.is_valid():
            profile = form.save(commit=False)
            profile.save()
            form.save_m2m()
            return redirect('assignments:tasker_profile')
    else:
        form = TaskerProfileForm(instance=tasker)
    
    # Get tasker's assignments
    assignments = Assignment.objects.filter(assigned_to=tasker)
    
    context = {
        'form': form,
        'tasker': tasker,
        'assignments': assignments,
    }
    
    return render(request, 'assignments/tasker_profile.html', context)


@method_decorator(require_any_role(UserRole.RoleType.MANAGER, UserRole.RoleType.ADMIN), name="dispatch")
class TaskerListView(LoginRequiredMixin, ListView):
    """List available taskers for assignment creators"""
    model = TaskerProfile
    template_name = 'assignments/tasker_list.html'
    context_object_name = 'taskers'
    paginate_by = 20

    def get_queryset(self):
        queryset = TaskerProfile.objects.filter(is_active_tasker=True)
        
        # Filter by skill level
        skill_level = self.request.GET.get('skill_level')
        if skill_level:
            queryset = queryset.filter(skill_level=skill_level)
        
        # Search by skills
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(skills__icontains=search)
        
        return queryset


# ============ Verification Helpers ============

def _persist_submission_verification(submission):
    rubric = submission.assignment.verification_rubric if isinstance(submission.assignment.verification_rubric, dict) else None
    verification_payload = run_assignment_verification(
        content=submission.submission_text or submission.assignment.description or submission.assignment.title,
        title=submission.assignment.title,
        description=submission.assignment.description,
        required_skills=submission.assignment.required_skills,
        rubric=rubric,
    )

    verification, _ = AssignmentVerification.objects.update_or_create(
        submission=submission,
        defaults={
            "assignment": submission.assignment,
            "status": AssignmentVerification.VerificationStatus.COMPLETED,
            "academic_field": verification_payload.get("academic_field", "humanities"),
            "subfield": verification_payload.get("subfield", ""),
            "submission_type": verification_payload.get("submission_type", "document"),
            "overall_score": verification_payload.get("overall_score", 0.0),
            "passed": verification_payload.get("passed", False),
            "verification_results": verification_payload,
            "issues_found": verification_payload.get("issues", []),
            "suggestions": verification_payload.get("suggestions", []),
            "started_at": timezone.now(),
            "completed_at": timezone.now(),
        },
    )

    verification.checks.all().delete()
    for check in verification_payload.get("checks", []):
        AssignmentVerificationCheck.objects.create(
            verification=verification,
            check_type=check.get("check_type", "general"),
            score=check.get("score", 0.0),
            details=check.get("details", {}),
            passed=check.get("score", 0.0) >= 70,
        )

    return verification, verification_payload


# ============ Submission Views ============

@require_tasker
@login_required
def submit_assignment(request, assignment_id):
    """Submit completed assignment"""
    assignment = get_object_or_404(Assignment, pk=assignment_id)
    tasker = get_object_or_404(TaskerProfile, user=request.user)
    
    if assignment.assigned_to != tasker:
        return redirect('assignments:assignment_detail', pk=assignment_id)
    
    if request.method == 'POST':
        form = AssignmentSubmissionForm(request.POST)
        if form.is_valid():
            submission = form.save(commit=False)
            submission.assignment = assignment
            submission.tasker = tasker
            submission.save()
            verification, payload = _persist_submission_verification(submission)
            messages.success(
                request,
                f"Submission saved and AI verification completed at {verification.overall_score:.1f}/100.",
            )
            return redirect('assignments:assignment_detail', pk=assignment_id)
    else:
        form = AssignmentSubmissionForm()
    
    return render(request, 'assignments/submit_assignment.html', {
        'form': form,
        'assignment': assignment,
        'assignment_verification_rubric': _assignment_verification_rubric(assignment),
    })


@login_required
def review_submission(request, submission_id):
    """Review a tasker's submission"""
    submission = get_object_or_404(AssignmentSubmission, pk=submission_id)
    
    if submission.assignment.creator != request.user:
        return redirect('assignments:assignment_detail', pk=submission.assignment.id)
    
    if request.method == 'POST':
        submission.status = request.POST.get('status', 'pending')
        submission.reviewer_notes = request.POST.get('reviewer_notes', '')
        rating = request.POST.get('rating')
        submission.rating = int(rating) if rating not in (None, "") else None
        submission.reviewed_by = request.user
        submission.reviewed_at = timezone.now()
        submission.save()
        
        # Update assignment if approved
        if submission.status == 'approved':
            submission.assignment.status = 'completed'
            submission.assignment.completed_at = timezone.now()
            
            # Update tasker success rate
            tasker = submission.tasker
            tasker.completed_assignments += 1
            total_assignments = tasker.assignments.count()
            # Recalculate success rate across all assignments assigned to this tasker.
            tasker.success_rate = (
                (tasker.completed_assignments / total_assignments) * 100
                if total_assignments > 0
                else 0
            )
            tasker.save()
            
            submission.assignment.save()
        
        return redirect('assignments:assignment_detail', pk=submission.assignment.id)
    
    return render(request, 'assignments/review_submission.html', {
        'submission': submission
    })
