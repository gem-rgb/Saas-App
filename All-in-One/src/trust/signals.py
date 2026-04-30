from django.db.models.signals import post_save
from django.dispatch import receiver

from assignments.models import TaskerProfile
from marketplace.permissions import ROLE_GROUPS
from trust.models import TaskerApplication
from trust.services import score_application


@receiver(post_save, sender=TaskerApplication)
def sync_tasker_profile(sender, instance, created, **kwargs):
    if instance.status != TaskerApplication.Status.APPROVED:
        return

    tasker_profile, _ = TaskerProfile.objects.get_or_create(user=instance.applicant)
    tasker_profile.skills = ", ".join(area.name for area in instance.competency_areas.all()) or tasker_profile.skills
    tasker_profile.bio = instance.bio or tasker_profile.bio
    tasker_profile.skill_level = "expert" if instance.years_experience >= 5 else "advanced" if instance.years_experience >= 3 else "intermediate"
    tasker_profile.trust_score = max(tasker_profile.trust_score, score_application(instance))
    tasker_profile.kyc_status = "approved"
    tasker_profile.competency_status = "approved"
    tasker_profile.interview_status = "passed" if instance.interview_confidence >= 70 else "under_review"
    tasker_profile.approval_status = "approved"
    tasker_profile.admin_approved = True
    tasker_profile.is_active_tasker = True
    tasker_profile.is_accepting_work = True
    tasker_profile.save()
    tasker_profile.competency_areas.set(instance.competency_areas.all())
    TaskerApplication.objects.filter(pk=instance.pk).update(tasker_profile=tasker_profile)

    groups = instance.applicant.groups
    from django.contrib.auth.models import Group

    tasker_group, _ = Group.objects.get_or_create(name=ROLE_GROUPS["tasker"])
    groups.add(tasker_group)
