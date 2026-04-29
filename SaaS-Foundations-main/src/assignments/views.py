from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.generic import ListView, DetailView, CreateView, UpdateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.db.models import Q
from django.utils import timezone

from .models import Assignment, AssignmentFile, TaskerProfile, AssignmentSubmission
from .forms import AssignmentForm, AssignmentFileForm, TaskerProfileForm, AssignmentSubmissionForm
from analytics.ml_engine import match_assignment_to_taskers


# ============ Dashboard Views ============

@login_required
def assignment_dashboard(request):
    """Main dashboard for assignment management"""
    user = request.user
    
    # Get user role
    is_tasker = hasattr(user, 'tasker_profile')
    
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
        queryset = Assignment.objects.all()
        
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
        
        # Filter by assigned_to if tasker
        if hasattr(self.request.user, 'tasker_profile'):
            queryset = queryset.filter(assigned_to=self.request.user.tasker_profile)
        
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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        assignment = self.get_object()
        context['files'] = assignment.files.all()
        context['submissions'] = assignment.submissions.all()
        context['is_creator'] = assignment.creator == self.request.user
        context['is_assigned_tasker'] = (
            hasattr(self.request.user, 'tasker_profile') and 
            assignment.assigned_to == self.request.user.tasker_profile
        )
        return context


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

@login_required
def tasker_profile_view(request):
    """View or create tasker profile"""
    tasker, created = TaskerProfile.objects.get_or_create(user=request.user)
    
    if request.method == 'POST':
        form = TaskerProfileForm(request.POST, instance=tasker)
        if form.is_valid():
            form.save()
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


# ============ Submission Views ============

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
            return redirect('assignments:assignment_detail', pk=assignment_id)
    else:
        form = AssignmentSubmissionForm()
    
    return render(request, 'assignments/submit_assignment.html', {
        'form': form,
        'assignment': assignment
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
