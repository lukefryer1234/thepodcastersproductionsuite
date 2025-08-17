from django.db import models
from django.contrib.auth.models import User

class AudioFile(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    audio_file = models.FileField(upload_to='audio_files/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

class ProcessedAudioFile(models.Model):
    original_file = models.ForeignKey(AudioFile, on_delete=models.CASCADE)
    processed_file = models.FileField(upload_to='processed_audio_files/')
    processed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Processed version of {self.original_file.title}"

class ShowNotes(models.Model):
    audio_file = models.ForeignKey(AudioFile, on_delete=models.CASCADE)
    notes = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Show notes for {self.audio_file.title}"

class SubscriptionPlan(models.Model):
    name = models.CharField(max_length=100)
    stripe_price_id = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=6, decimal_places=2)
    processing_hours = models.IntegerField()

    def __str__(self):
        return self.name

class UserSubscription(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    stripe_customer_id = models.CharField(max_length=100, blank=True, null=True)
    subscription_plan = models.ForeignKey(SubscriptionPlan, on_delete=models.SET_NULL, null=True, blank=True)
    stripe_subscription_id = models.CharField(max_length=100, blank=True, null=True)
    is_active = models.BooleanField(default=False)
    remaining_processing_hours = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.user.username}'s subscription"
