from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand

from marketplace.models import TaskCategory
from operations.models import Region
from trust.models import CompetencyArea


DEFAULT_CATEGORIES = [
    ("essays", "Essays"),
    ("programming", "Programming"),
    ("statistics", "Statistics"),
    ("nursing", "Nursing"),
    ("law", "Law"),
    ("engineering", "Engineering"),
    ("research", "Research"),
    ("presentations", "Presentations"),
]

DEFAULT_COMPETENCIES = [
    ("essays", "Essays"),
    ("programming", "Programming"),
    ("statistics", "Statistics"),
    ("nursing", "Nursing"),
    ("law", "Law"),
    ("engineering", "Engineering"),
]

DEFAULT_REGIONS = [
    ("alaska-region", "Alaska Region", "America/Anchorage"),
    ("east-coast-region", "East Coast Region", "America/New_York"),
    ("europe-region", "Europe Region", "Europe/London"),
]

DEFAULT_GROUPS = ["Student", "Tasker", "Manager", "Admin"]


class Command(BaseCommand):
    help = "Seed the academic task marketplace with baseline roles, regions, and competency categories."

    def handle(self, *args, **options):
        for group_name in DEFAULT_GROUPS:
            Group.objects.get_or_create(name=group_name)

        for slug, name in DEFAULT_CATEGORIES:
            TaskCategory.objects.get_or_create(
                slug=slug,
                defaults={"name": name, "description": f"{name} tasks", "order": 10},
            )

        for slug, name in DEFAULT_COMPETENCIES:
            CompetencyArea.objects.get_or_create(
                slug=slug,
                defaults={"name": name, "description": f"{name} competency area", "order": 10},
            )

        for code, name, timezone_name in DEFAULT_REGIONS:
            Region.objects.get_or_create(
                code=code,
                defaults={"name": name, "timezone": timezone_name, "description": f"{name} coverage region"},
            )

        self.stdout.write(self.style.SUCCESS("Marketplace bootstrap completed."))

