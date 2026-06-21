from django import forms
from django.contrib.auth.forms import AuthenticationForm

from .models import (
    Task,
    Complaint,
    SubTask
)

from django import forms
from django.contrib.auth.models import User # <-- ADD THIS LINE
from .models import Task


class TaskForm(forms.ModelForm):
    assigned_technicians = forms.ModelMultipleChoiceField(
        # Try removing the .filter() first to see if names appear.
        # If they do, your filter logic (profile__role) is the problem.
        queryset=User.objects.all(),
        widget=forms.SelectMultiple(attrs={'class': 'form-select'}),
        required=False,
        label="Assigned Technicians (المسؤولون)")

    def clean_maintenance_work(self):
        value = self.cleaned_data.get("maintenance_work")

        if value:
            exists = MaintenanceWorkItem.objects.filter(
                name__iexact=value.strip()
            ).exists()

            if not exists:
                raise forms.ValidationError(
                    "Please select a maintenance work from the list."
                )

        return value
    class Meta:
        model = Task
        exclude = [
            'title',  # Excluded since it's handled automatically or hidden
            'supervisor',  # Removed as requested
            'budget',  # Removed as requested
            'job_id',
            'started_at',
            'completed_at',
            'is_overdue',
            'created_at',
            'reward_points_awarded',
            'is_rewarded'
        ]

        widgets = {
            # Use flatpickr class for JavaScript initialization
            'start_date': forms.TextInput(
                attrs={'class': 'flatpickr-input', 'placeholder': 'Select Start Date & Time'}),
            'deadline': forms.TextInput(
                attrs={'class': 'flatpickr-input', 'placeholder': 'Select Deadline Date & Time'}),
        }

    # --- INDENTATION FIXED: This is now placed outside class Meta ---
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Tell Django to accept both Date and Time input formats
        self.fields['start_date'].input_formats = ['%Y-%m-%d %H:%M', '%d/%m/%Y %H:%M']
        self.fields['deadline'].input_formats = ['%Y-%m-%d %H:%M', '%d/%m/%Y %H:%M']

        # Apply standard form classes to basic fields dynamically
        for name, field in self.fields.items():
            field.widget.attrs.update({'class': 'form-control'})

        # Define Dropdown Picker Matrix options explicitly
        BUILDING_CHOICES = [
            ('', '-- Select Building (اختر البناية) --'),
            ('Aliya Villa (فيلا عليا)', 'Aliya Villa (فيلا عليا)'),
            ('Al Farah Plaza (بلازا الفرح)', 'Al Farah Plaza (بلازا الفرح)'),
            ('Al Huda Building (بناية الهدى)', 'Al Huda Building (بناية الهدى)'),
            ('Al Ithihad Building (بناية الاتحاد)', 'Al Ithihad Building (بناية الاتحاد)'),
            ('Al Khaleej Building (بناية الخليج)', 'Al Khaleej Building (بناية الخليج)'),
            ('Al Maktab Building (بناية المكتب)', 'Al Maktab Building (بناية المكتب)'),
            ('Al Maass Building (بناية الماس)', 'Al Maass Building (بناية الماس)'),
            ('Al Naser Plaza (بلازا النصر)', 'Al Naser Plaza (بلازا النصر)'),
            ('Al Raihan Plaza (بلازا الريحان)', 'Al Raihan Plaza (بلازا الريحان)'),
            ('Al Salam Building (بناية السلام)', 'Al Salam Building (بناية السلام)'),
            ('Arbab House (YBN) (منزل أرباب YBN)', 'Arbab House (YBN) (منزل أرباب YBN)'),
            ('Bader Building (بناية بدر)', 'Bader Building (بناية بدر)'),
            ('Fatma YBN Villa (فيلا فاطمة YBN)', 'Fatma YBN Villa (فيلا فاطمة YBN)'),
            ('Farm Helio (مزرعة هيليو)', 'Farm Helio (مزرعة هيليو)'),
            (
            'Mohammed Yousef Nasser Villa (فيلا محمد يوسف ناصر)', 'Mohammed Yousef Nasser Villa (فيلا محمد يوسف ناصر)'),
            ('Muhammed Yousuf Building (بناية محمد يوسف)', 'Muhammed Yousuf Building (بناية محمد يوسف)'),
            ('Rashidiya Building (بناية الرشيدية)', 'Rashidiya Building (بناية الرشيدية)'),
            ('Sanahiya Building (بناية الصناعية)', 'Sanahiya Building (بناية الصناعية)'),
            ('Souk Building (بناية السوق)', 'Souk Building (بناية السوق)'),
            ('Villa Sanahiya (فيلا الصناعية)', 'Villa Sanahiya (فيلا الصناعية)'),
            ('Other (آخر)', 'Other (آخر)')
        ]

        # Explicitly force fields to render as Dropdown select widgets
        self.fields['building'].widget = forms.Select(choices=BUILDING_CHOICES, attrs={'class': 'form-select'})
        self.fields['unit'].widget = forms.Select(choices=[('', '-- Select Unit First --')],
                                                  attrs={'class': 'form-select'})

        self.fields['custom_location'].widget = forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Specify missing building/unit details manually here...',
            'style': 'display: none;'
        })

        # Ensure custom fields match required criteria safely
        self.fields['building'].required = True
        self.fields['unit'].required = True
        self.fields['custom_location'].required = False

class ComplaintForm(forms.ModelForm):

    class Meta:

        model = Complaint

        fields = [

            'message',


        ]


class SubTaskForm(forms.ModelForm):

    class Meta:

        model = SubTask

        fields = ['title']


class CustomLoginForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['username'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'Username'
        })

        self.fields['password'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'Password'
        })