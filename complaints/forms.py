from django import forms

from .models import CanonicalStatus


class CaseWorkflowForm(forms.Form):
    status = forms.ChoiceField(choices=CanonicalStatus.choices)
    next_action = forms.CharField(
        max_length=240, required=False,
        widget=forms.TextInput(attrs={"placeholder": "What needs to happen next?"}),
    )
    sla_due_at = forms.DateTimeField(
        required=False,
        input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S"],
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
        label="SLA deadline",
    )
    remarks = forms.CharField(
        max_length=4000,
        widget=forms.Textarea(attrs={"rows": 4, "placeholder": "Record the action taken and its outcome."}),
    )

