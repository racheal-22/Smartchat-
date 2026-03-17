from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import CustomUser, StudentProfile


@receiver(post_save, sender=CustomUser)
def create_student_profile(sender, instance, created, **kwargs):
    if created and instance.role == "student":
        StudentProfile.objects.create(user=instance)
