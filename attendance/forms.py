from django import forms

from .models import AttendanceRecord, Course


class CourseForm(forms.ModelForm):
    class Meta:
        model = Course
        fields = ["name", "code"]


class StartSessionForm(forms.Form):
    duration_minutes = forms.IntegerField(
        label="Süre (dakika)", min_value=1, max_value=180, initial=15
    )


class CheckinForm(forms.ModelForm):
    device_id = forms.CharField(max_length=64, required=False, widget=forms.HiddenInput)

    class Meta:
        model = AttendanceRecord
        fields = ["first_name", "last_name", "student_number"]

    def clean_student_number(self):
        number = self.cleaned_data["student_number"].strip()
        if not number.isdigit():
            raise forms.ValidationError("Öğrenci numarası yalnızca rakamlardan oluşmalı.")
        return number

    # Not: .title()/.upper() kullanmıyoruz; Python bunları Türkçe kurallarına
    # göre yapmaz ("irem".title() -> "Irem", doğrusu "İrem").
    def clean_first_name(self):
        return " ".join(self.cleaned_data["first_name"].split())

    def clean_last_name(self):
        return " ".join(self.cleaned_data["last_name"].split())
