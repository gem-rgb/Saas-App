from django import forms

from trust.models import AIInterviewSession, CompetencyArea, IdentityVerification, TaskerApplication, TaskerDocument


BASE_INPUT = "w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-slate-900 shadow-sm focus:border-cyan-500 focus:ring-cyan-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"


class TaskerApplicationForm(forms.ModelForm):
    competency_areas = forms.ModelMultipleChoiceField(
        queryset=CompetencyArea.objects.filter(active=True).order_by("order", "name"),
        widget=forms.CheckboxSelectMultiple,
        required=False,
    )

    class Meta:
        model = TaskerApplication
        fields = [
            "headline",
            "bio",
            "years_experience",
            "education_level",
            "portfolio_url",
            "region_preference",
            "competency_areas",
        ]
        widgets = {
            "headline": forms.TextInput(attrs={"class": BASE_INPUT, "placeholder": "Headline"}),
            "bio": forms.Textarea(attrs={"class": BASE_INPUT, "rows": 4, "placeholder": "Tell us about your experience"}),
            "years_experience": forms.NumberInput(attrs={"class": BASE_INPUT, "min": 0}),
            "education_level": forms.TextInput(attrs={"class": BASE_INPUT, "placeholder": "Education level"}),
            "portfolio_url": forms.URLInput(attrs={"class": BASE_INPUT, "placeholder": "https://portfolio.example.com"}),
            "region_preference": forms.Select(attrs={"class": BASE_INPUT}),
        }


class TaskerDocumentForm(forms.ModelForm):
    class Meta:
        model = TaskerDocument
        fields = ["document_type", "file", "description"]
        widgets = {
            "document_type": forms.Select(attrs={"class": BASE_INPUT}),
            "file": forms.FileInput(attrs={"class": BASE_INPUT}),
            "description": forms.Textarea(attrs={"class": BASE_INPUT, "rows": 3, "placeholder": "Optional note"}),
        }


class IdentityVerificationForm(forms.ModelForm):
    class Meta:
        model = IdentityVerification
        fields = ["selfie_image", "id_front_image", "id_back_image"]
        widgets = {
            "selfie_image": forms.FileInput(attrs={"class": BASE_INPUT}),
            "id_front_image": forms.FileInput(attrs={"class": BASE_INPUT}),
            "id_back_image": forms.FileInput(attrs={"class": BASE_INPUT}),
        }


class InterviewSessionForm(forms.ModelForm):
    class Meta:
        model = AIInterviewSession
        fields = ["mode"]
        widgets = {
            "mode": forms.Select(attrs={"class": BASE_INPUT}),
        }

