from django import forms

from marketplace.models import (
    TaskAttachment,
    TaskOrder,
    TaskRating,
    TaskRevisionRequest,
    TaskSubmission,
)


BASE_INPUT = "w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-slate-900 shadow-sm focus:border-cyan-500 focus:ring-cyan-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
RUBRIC_INPUT = (
    "w-full rounded-xl border border-slate-300 bg-white px-4 py-3 font-mono text-sm text-slate-900 shadow-sm "
    "focus:border-cyan-500 focus:ring-cyan-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
)


class TaskOrderForm(forms.ModelForm):
    verification_rubric = forms.JSONField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": RUBRIC_INPUT,
                "rows": 8,
                "placeholder": '{\n  "title": "Short Answer Rubric",\n  "answer_type": "short_text",\n  "grading_style": "partial",\n  "minimum_score": 70,\n  "criteria": [\n    {\n      "name": "Definition accuracy",\n      "weight": 4,\n      "required_terms": ["sunlight", "energy conversion"]\n    }\n  ]\n}',
            }
        ),
    )

    class Meta:
        model = TaskOrder
        fields = [
            "title",
            "subject",
            "category",
            "competency_area",
            "description",
            "instructions",
            "deadline",
            "estimated_hours",
            "budget_cents",
            "complexity_level",
            "region_preference",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"class": BASE_INPUT, "placeholder": "Assignment title"}),
            "subject": forms.TextInput(attrs={"class": BASE_INPUT, "placeholder": "Academic subject"}),
            "category": forms.Select(attrs={"class": BASE_INPUT}),
            "competency_area": forms.Select(attrs={"class": BASE_INPUT}),
            "description": forms.Textarea(attrs={"class": BASE_INPUT, "rows": 4, "placeholder": "Task summary"}),
            "instructions": forms.Textarea(attrs={"class": BASE_INPUT, "rows": 8, "placeholder": "Detailed instructions, grading rubric, and special notes"}),
            "deadline": forms.DateTimeInput(attrs={"class": BASE_INPUT, "type": "datetime-local"}),
            "estimated_hours": forms.NumberInput(attrs={"class": BASE_INPUT, "min": 1}),
            "budget_cents": forms.NumberInput(attrs={"class": BASE_INPUT, "min": 0, "placeholder": "Budget in cents"}),
            "complexity_level": forms.Select(attrs={"class": BASE_INPUT}),
            "region_preference": forms.Select(attrs={"class": BASE_INPUT}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        metadata = self.instance.metadata if isinstance(getattr(self.instance, "metadata", None), dict) else {}
        if metadata.get("verification_rubric"):
            self.fields["verification_rubric"].initial = metadata["verification_rubric"]

    def clean_verification_rubric(self):
        rubric = self.cleaned_data.get("verification_rubric")
        if rubric in (None, ""):
            return {}
        if not isinstance(rubric, dict):
            raise forms.ValidationError("Rubric must be a JSON object.")
        return rubric

    def save(self, commit=True):
        instance = super().save(commit=False)
        metadata = instance.metadata if isinstance(instance.metadata, dict) else {}
        metadata["verification_rubric"] = self.cleaned_data.get("verification_rubric") or {}
        instance.metadata = metadata
        if commit:
            instance.save()
        return instance


class TaskAttachmentForm(forms.ModelForm):
    class Meta:
        model = TaskAttachment
        fields = ["file", "file_kind", "description"]
        widgets = {
            "file": forms.FileInput(attrs={"class": BASE_INPUT}),
            "file_kind": forms.Select(attrs={"class": BASE_INPUT}),
            "description": forms.Textarea(attrs={"class": BASE_INPUT, "rows": 3, "placeholder": "Optional note"}),
        }


class TaskSubmissionForm(forms.ModelForm):
    class Meta:
        model = TaskSubmission
        fields = ["submission_text", "file", "summary"]
        widgets = {
            "submission_text": forms.Textarea(attrs={"class": BASE_INPUT, "rows": 8, "placeholder": "Submission content"}),
            "file": forms.FileInput(attrs={"class": BASE_INPUT}),
            "summary": forms.Textarea(attrs={"class": BASE_INPUT, "rows": 3, "placeholder": "Short delivery summary"}),
        }


class TaskRevisionRequestForm(forms.ModelForm):
    class Meta:
        model = TaskRevisionRequest
        fields = ["reason", "due_at"]
        widgets = {
            "reason": forms.Textarea(attrs={"class": BASE_INPUT, "rows": 4, "placeholder": "Explain what needs revision"}),
            "due_at": forms.DateTimeInput(attrs={"class": BASE_INPUT, "type": "datetime-local"}),
        }


class TaskRatingForm(forms.ModelForm):
    class Meta:
        model = TaskRating
        fields = ["overall_rating", "accuracy_rating", "communication_rating", "speed_rating", "comments"]
        widgets = {
            "overall_rating": forms.NumberInput(attrs={"class": BASE_INPUT, "min": 1, "max": 5}),
            "accuracy_rating": forms.NumberInput(attrs={"class": BASE_INPUT, "min": 1, "max": 5}),
            "communication_rating": forms.NumberInput(attrs={"class": BASE_INPUT, "min": 1, "max": 5}),
            "speed_rating": forms.NumberInput(attrs={"class": BASE_INPUT, "min": 1, "max": 5}),
            "comments": forms.Textarea(attrs={"class": BASE_INPUT, "rows": 4, "placeholder": "Share your feedback"}),
        }


TASK_MESSAGE_AUDIENCE_CHOICES = (
    ("shared", "Shared with student"),
    ("team", "Task team only"),
    ("internal", "Managers only"),
)


class TaskConversationMessageForm(forms.Form):
    message = forms.CharField(
        widget=forms.Textarea(
            attrs={
                "class": BASE_INPUT,
                "rows": 4,
                "placeholder": "Send an update, question, or instruction...",
            }
        )
    )
    audience = forms.ChoiceField(
        choices=TASK_MESSAGE_AUDIENCE_CHOICES,
        initial="shared",
        widget=forms.Select(attrs={"class": BASE_INPUT}),
    )
