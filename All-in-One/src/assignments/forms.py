from django import forms
from .models import Assignment, AssignmentFile, TaskerProfile, AssignmentSubmission


class AssignmentForm(forms.ModelForm):
    class Meta:
        model = Assignment
        fields = ['title', 'description', 'required_skills', 'priority', 'deadline', 'estimated_hours', 'budget_cents']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg dark:bg-gray-700 dark:border-gray-600',
                'placeholder': 'Assignment title'
            }),
            'description': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg dark:bg-gray-700 dark:border-gray-600',
                'rows': 5,
                'placeholder': 'Detailed description of the assignment'
            }),
            'required_skills': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg dark:bg-gray-700 dark:border-gray-600',
                'placeholder': 'e.g., Python, Data Analysis, Machine Learning'
            }),
            'priority': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg dark:bg-gray-700 dark:border-gray-600'
            }),
            'deadline': forms.DateTimeInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg dark:bg-gray-700 dark:border-gray-600',
                'type': 'datetime-local'
            }),
            'estimated_hours': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg dark:bg-gray-700 dark:border-gray-600',
                'placeholder': 'Estimated hours needed'
            }),
            'budget_cents': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg dark:bg-gray-700 dark:border-gray-600',
                'placeholder': 'Budget in cents (optional)'
            }),
        }


class AssignmentFileForm(forms.ModelForm):
    class Meta:
        model = AssignmentFile
        fields = ['file', 'file_type', 'description']
        widgets = {
            'file': forms.FileInput(attrs={
                'class': 'block w-full text-sm text-gray-900 dark:text-gray-300',
                'accept': '.pdf,.doc,.docx,.txt,.xlsx,.csv,.zip,.jpg,.png,.py,.js,.json'
            }),
            'file_type': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg dark:bg-gray-700 dark:border-gray-600',
                'placeholder': 'e.g., instruction, data, reference'
            }),
            'description': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg dark:bg-gray-700 dark:border-gray-600',
                'rows': 3,
                'placeholder': 'Optional description'
            }),
        }


class TaskerProfileForm(forms.ModelForm):
    class Meta:
        model = TaskerProfile
        fields = ['skills', 'skill_level', 'bio', 'availability_hours_per_week']
        widgets = {
            'skills': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg dark:bg-gray-700 dark:border-gray-600',
                'rows': 3,
                'placeholder': 'Python, Data Analysis, Machine Learning'
            }),
            'skill_level': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg dark:bg-gray-700 dark:border-gray-600'
            }),
            'bio': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg dark:bg-gray-700 dark:border-gray-600',
                'rows': 4,
                'placeholder': 'Tell us about your experience'
            }),
            'availability_hours_per_week': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg dark:bg-gray-700 dark:border-gray-600',
                'placeholder': 'Hours available per week'
            }),
        }


class AssignmentSubmissionForm(forms.ModelForm):
    class Meta:
        model = AssignmentSubmission
        fields = ['submission_text']
        widgets = {
            'submission_text': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg dark:bg-gray-700 dark:border-gray-600',
                'rows': 8,
                'placeholder': 'Submit your completed work here...'
            }),
        }
