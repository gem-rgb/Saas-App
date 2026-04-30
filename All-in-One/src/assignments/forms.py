from django import forms
from trust.models import CompetencyArea
from .models import Assignment, AssignmentFile, TaskerProfile, AssignmentSubmission


RUBRIC_INPUT = (
    "w-full px-4 py-2 border border-gray-300 rounded-lg font-mono text-sm dark:bg-gray-700 dark:border-gray-600"
)


class AssignmentForm(forms.ModelForm):
    verification_rubric = forms.JSONField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": RUBRIC_INPUT,
                "rows": 8,
                "placeholder": '{\n  "title": "Essay Rubric",\n  "answer_type": "essay",\n  "grading_style": "feedback-heavy",\n  "minimum_score": 70,\n  "criteria": [\n    {\n      "name": "Thesis clarity",\n      "weight": 4,\n      "required_terms": ["clear thesis", "main argument"]\n    }\n  ]\n}',
            }
        ),
    )

    class Meta:
        model = Assignment
        fields = ['title', 'description', 'required_skills', 'priority', 'deadline', 'estimated_hours', 'budget_cents', 'verification_rubric']
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if getattr(self.instance, "pk", None) and self.instance.verification_rubric:
            self.fields["verification_rubric"].initial = self.instance.verification_rubric

    def clean_verification_rubric(self):
        rubric = self.cleaned_data.get("verification_rubric")
        if rubric in (None, ""):
            return {}
        if not isinstance(rubric, dict):
            raise forms.ValidationError("Rubric must be a JSON object.")
        return rubric

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.verification_rubric = self.cleaned_data.get("verification_rubric") or {}
        if commit:
            instance.save()
        return instance


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
    competency_areas = forms.ModelMultipleChoiceField(
        queryset=CompetencyArea.objects.filter(active=True).order_by("order", "name"),
        widget=forms.CheckboxSelectMultiple,
        required=False,
    )

    class Meta:
        model = TaskerProfile
        fields = ['skills', 'skill_level', 'bio', 'availability_hours_per_week', 'competency_areas']
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if getattr(self.instance, "pk", None):
            self.fields["competency_areas"].initial = self.instance.competency_areas.all()


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
