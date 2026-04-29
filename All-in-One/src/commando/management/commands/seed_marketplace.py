"""
Seed data for the Academic Task Marketplace.
Creates CompetencyAreas, TaskCategories, and Regions.
"""
from django.core.management.base import BaseCommand
from django.utils.text import slugify


class Command(BaseCommand):
    help = "Seed the database with marketplace competency areas, task categories, and regions."

    def handle(self, *args, **options):
        self._seed_competency_areas()
        self._seed_task_categories()
        self._seed_regions()
        self.stdout.write(self.style.SUCCESS("Seed data loaded successfully."))

    def _seed_competency_areas(self):
        from trust.models import CompetencyArea

        areas = [
            ("Essays", "essays"),
            ("Programming", "programming"),
            ("Statistics", "statistics"),
            ("Nursing", "nursing"),
            ("Law", "law"),
            ("Engineering", "engineering"),
            ("Business & Finance", "business-finance"),
            ("Mathematics", "mathematics"),
            ("Biology & Life Sciences", "biology-life-sciences"),
            ("Psychology", "psychology"),
            ("History", "history"),
            ("Political Science", "political-science"),
            ("Computer Science", "computer-science"),
            ("Data Science & ML", "data-science-ml"),
            ("Sociology", "sociology"),
            ("Education", "education"),
            ("Marketing", "marketing"),
            ("Accounting", "accounting"),
        ]
        created = 0
        for order, (name, slug) in enumerate(areas, start=1):
            _, was_created = CompetencyArea.objects.get_or_create(
                slug=slug,
                defaults={"name": name, "order": order, "active": True},
            )
            if was_created:
                created += 1
        self.stdout.write(f"  CompetencyAreas: {created} created, {len(areas) - created} already existed.")

    def _seed_task_categories(self):
        from marketplace.models import TaskCategory

        categories = [
            ("Essay Writing", "essay-writing", "pencil"),
            ("Research Paper", "research-paper", "book-open"),
            ("Case Study", "case-study", "briefcase"),
            ("Lab Report", "lab-report", "beaker"),
            ("Dissertation Chapter", "dissertation-chapter", "academic-cap"),
            ("Programming Project", "programming-project", "code-bracket"),
            ("Statistics Analysis", "statistics-analysis", "chart-bar"),
            ("Math Problem Set", "math-problem-set", "calculator"),
            ("Presentation", "presentation", "presentation-chart-bar"),
            ("Literature Review", "literature-review", "book-open"),
            ("Business Plan", "business-plan", "chart-pie"),
            ("Technical Report", "technical-report", "document-text"),
        ]
        created = 0
        for order, (name, slug, icon) in enumerate(categories, start=1):
            _, was_created = TaskCategory.objects.get_or_create(
                slug=slug,
                defaults={"name": name, "icon": icon, "order": order, "active": True},
            )
            if was_created:
                created += 1
        self.stdout.write(f"  TaskCategories: {created} created, {len(categories) - created} already existed.")

    def _seed_regions(self):
        from operations.models import Region

        regions = [
            ("us-west", "US West Coast", "America/Los_Angeles", ["US"]),
            ("us-east", "US East Coast", "America/New_York", ["US"]),
            ("us-central", "US Central", "America/Chicago", ["US"]),
            ("alaska", "Alaska", "America/Anchorage", ["US"]),
            ("canada", "Canada", "America/Toronto", ["CA"]),
            ("uk-ireland", "UK & Ireland", "Europe/London", ["GB", "IE"]),
            ("europe-west", "Western Europe", "Europe/Berlin", ["DE", "FR", "NL", "BE"]),
            ("europe-east", "Eastern Europe", "Europe/Warsaw", ["PL", "CZ", "RO", "HU"]),
            ("africa-east", "East Africa", "Africa/Nairobi", ["KE", "UG", "TZ"]),
            ("africa-west", "West Africa", "Africa/Lagos", ["NG", "GH"]),
            ("africa-south", "Southern Africa", "Africa/Johannesburg", ["ZA", "BW"]),
            ("asia-south", "South Asia", "Asia/Kolkata", ["IN", "PK", "BD"]),
            ("asia-southeast", "Southeast Asia", "Asia/Singapore", ["SG", "MY", "PH"]),
            ("oceania", "Australia & New Zealand", "Australia/Sydney", ["AU", "NZ"]),
        ]
        created = 0
        for code, name, tz, countries in regions:
            _, was_created = Region.objects.get_or_create(
                code=code,
                defaults={
                    "name": name,
                    "timezone": tz,
                    "countries": countries,
                    "active": True,
                    "staff_target": 10,
                },
            )
            if was_created:
                created += 1
        self.stdout.write(f"  Regions: {created} created, {len(regions) - created} already existed.")
