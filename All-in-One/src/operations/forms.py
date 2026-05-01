from django import forms

from operations.models import ManagerApplication, Region


BASE_INPUT = "w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-slate-900 shadow-sm focus:border-cyan-500 focus:ring-cyan-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"


class ManagerApplicationForm(forms.ModelForm):
    regions = forms.ModelMultipleChoiceField(
        queryset=Region.objects.filter(active=True).order_by("name"),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = ManagerApplication
        fields = [
            "title",
            "bio",
            "years_experience",
            "regions",
            "cv_file",
            "selfie_file",
            "id_front_file",
            "id_back_file",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"class": BASE_INPUT, "placeholder": "Operations Manager"}),
            "bio": forms.Textarea(attrs={"class": BASE_INPUT, "rows": 4, "placeholder": "Short summary of your management background"}),
            "years_experience": forms.NumberInput(attrs={"class": BASE_INPUT, "min": 0}),
            "cv_file": forms.FileInput(attrs={"class": BASE_INPUT}),
            "selfie_file": forms.FileInput(attrs={"class": BASE_INPUT}),
            "id_front_file": forms.FileInput(attrs={"class": BASE_INPUT}),
            "id_back_file": forms.FileInput(attrs={"class": BASE_INPUT}),
        }

