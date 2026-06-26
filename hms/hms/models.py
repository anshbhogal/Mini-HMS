import json
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone

class User(AbstractUser):
    ROLE_CHOICES = (
        ('doctor', 'Doctor'),
        ('patient', 'Patient'),
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='patient')
    full_name = models.CharField(max_length=150, blank=True)

    # Resolve reverse relation clashes
    groups = models.ManyToManyField(
        'auth.Group',
        related_name='hms_users_groups',
        blank=True,
        help_text='The groups this user belongs to.',
        verbose_name='groups',
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        related_name='hms_users_permissions',
        blank=True,
        help_text='Specific permissions for this user.',
        verbose_name='user permissions',
    )

    def get_display_name(self):
        if self.role == 'doctor':
            return f"Dr. {self.full_name or self.username}"
        return self.full_name or self.username

    def __str__(self):
        return f"{self.username} ({self.role})"


class Availability(models.Model):
    doctor = models.ForeignKey(User, on_delete=models.CASCADE, limit_choices_to={'role': 'doctor'}, related_name='availabilities')
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    is_booked = models.BooleanField(default=False)

    class Meta:
        verbose_name_plural = "Availabilities"
        ordering = ['start_time']

    def clean(self):
        if self.start_time and self.end_time:
            if self.start_time >= self.end_time:
                raise ValidationError("Start time must be strictly before end time.")
            if self.start_time < timezone.now():
                raise ValidationError("Cannot create availability slots in the past.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.doctor.username}: {self.start_time.strftime('%Y-%m-%d %H:%M')} to {self.end_time.strftime('%H:%M')}"


class Booking(models.Model):
    patient = models.ForeignKey(User, on_delete=models.CASCADE, limit_choices_to={'role': 'patient'}, related_name='bookings')
    doctor = models.ForeignKey(User, on_delete=models.CASCADE, limit_choices_to={'role': 'doctor'}, related_name='doctor_bookings')
    availability_slot = models.OneToOneField(Availability, on_delete=models.CASCADE, related_name='booking')
    created_at = models.DateTimeField(auto_now_add=True)
    
    doctor_google_event_id = models.CharField(max_length=255, blank=True, null=True)
    patient_google_event_id = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return f"Booking: {self.patient.username} with {self.doctor.username} on {self.availability_slot.start_time.strftime('%Y-%m-%d')}"


class GoogleCredentials(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='google_credentials')
    token = models.TextField()
    refresh_token = models.TextField(null=True, blank=True)
    token_uri = models.CharField(max_length=255)
    client_id = models.CharField(max_length=255)
    client_secret = models.CharField(max_length=255)
    scopes = models.TextField()  # JSON list of scopes

    def to_dict(self):
        return {
            'token': self.token,
            'refresh_token': self.refresh_token,
            'token_uri': self.token_uri,
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'scopes': json.loads(self.scopes) if self.scopes else []
        }

    @classmethod
    def from_dict(cls, user, cred_dict):
        scopes_json = json.dumps(cred_dict.get('scopes', []))
        obj, created = cls.objects.update_or_create(
            user=user,
            defaults={
                'token': cred_dict.get('token'),
                'refresh_token': cred_dict.get('refresh_token'),
                'token_uri': cred_dict.get('token_uri'),
                'client_id': cred_dict.get('client_id'),
                'client_secret': cred_dict.get('client_secret'),
                'scopes': scopes_json
            }
        )
        return obj

    def __str__(self):
        return f"Google Credentials for {self.user.username}"
