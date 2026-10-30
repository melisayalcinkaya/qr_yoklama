from django import forms

from .models import AttendanceRecord, Course


class CourseForm(forms.ModelForm):
    class Meta:
        model = Course
        fields = ["name", "code"]


class CourseSettingsForm(forms.ModelForm):
    class Meta:
        model = Course
        fields = ["name", "code", "location_enabled", "latitude", "longitude", "radius_m"]
        widgets = {
            "latitude": forms.NumberInput(attrs={"step": "any"}),
            "longitude": forms.NumberInput(attrs={"step": "any"}),
        }

    def clean(self):
        data = super().clean()
        if data.get("location_enabled"):
            lat, lon = data.get("latitude"), data.get("longitude")
            if lat is None or lon is None:
                raise forms.ValidationError(
                    "Konum doğrulaması için sınıfın konumunu girin ya da “Konumumu kullan” düğmesine basın."
                )
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise forms.ValidationError("Geçersiz koordinat.")
        return data


class StartSessionForm(forms.Form):
    duration_minutes = forms.IntegerField(
        label="Süre (dakika)", min_value=1, max_value=180, initial=15
    )


class CheckinForm(forms.ModelForm):
    device_id = forms.CharField(max_length=64, required=False, widget=forms.HiddenInput)
    # Konum alanları tarayıcı tarafından doldurulur; konum doğrulaması kapalıysa boş kalır.
    latitude = forms.FloatField(required=False, widget=forms.HiddenInput, min_value=-90, max_value=90)
    longitude = forms.FloatField(required=False, widget=forms.HiddenInput, min_value=-180, max_value=180)
    accuracy = forms.FloatField(required=False, widget=forms.HiddenInput, min_value=0)

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
