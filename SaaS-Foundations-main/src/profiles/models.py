from django.conf import settings
from django.db import models
from django.db.models.signals import post_save

User = settings.AUTH_USER_MODEL


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    bio = models.TextField(max_length=500, blank=True, default="")
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, default="")
    company = models.CharField(max_length=150, blank=True, default="")
    website = models.URLField(blank=True, default="")
    updated = models.DateTimeField(auto_now=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username}'s profile"

    @property
    def avatar_url(self):
        if self.avatar and hasattr(self.avatar, 'url'):
            return self.avatar.url
        return None

    @property
    def initials(self):
        first = self.user.first_name[:1] if self.user.first_name else ""
        last = self.user.last_name[:1] if self.user.last_name else ""
        if first or last:
            return f"{first}{last}".upper()
        return self.user.username[:2].upper()


def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.get_or_create(user=instance)


post_save.connect(create_user_profile, sender='auth.User')
