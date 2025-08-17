from django import forms
from django.contrib.auth.models import User
from .models import AudioFile

class RegistrationForm(forms.Form):
    username = forms.CharField(max_length=150)
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput)
    password2 = forms.CharField(label='Confirm password', widget=forms.PasswordInput)

    def clean_username(self):
        username = self.cleaned_data.get('username')
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError('A user with that username already exists.')
        return username

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError('A user with that email already exists.')
        return email

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        password2 = cleaned_data.get("password2")

        if password and password2 and password != password2:
            self.add_error('password2', 'Passwords do not match')

        return cleaned_data

from django.core.validators import FileExtensionValidator

class AudioFileForm(forms.ModelForm):
    class Meta:
        model = AudioFile
        fields = ['title', 'audio_file']
        widgets = {
            'audio_file': forms.ClearableFileInput(attrs={'accept': '.mp3,.wav,.m4a,.flac,.ogg'})
        }

    def __init__(self, *args, **kwargs):
        super(AudioFileForm, self).__init__(*args, **kwargs)
        self.fields['audio_file'].validators.append(
            FileExtensionValidator(allowed_extensions=['mp3', 'wav', 'm4a', 'flac', 'ogg'])
        )
