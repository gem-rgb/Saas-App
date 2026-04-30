"""
Management command to seed default subscription plans.
Usage: python manage.py seed_plans
"""
from django.core.management.base import BaseCommand
from subscriptions.models import Subscription, SubscriptionPrice


PLANS = [
    {
        "name": "Essential",
        "subtitle": "Perfect for students who need help with occasional assignments.",
        "order": 1,
        "features": "Up to 3 active tasks\nStandard matching\nEmail support\n48-hour turnaround\nBasic analytics",
        "prices": {
            "month": "9.99",
            "year": "99.99",
        },
    },
    {
        "name": "Pro",
        "subtitle": "For busy students who need consistent, reliable academic help.",
        "order": 2,
        "features": "Up to 10 active tasks\nPriority matching\nLive chat support\n24-hour turnaround\nAdvanced analytics\nRevision guarantee",
        "prices": {
            "month": "29.99",
            "year": "299.99",
        },
    },
    {
        "name": "Expert",
        "subtitle": "Unlimited access with a dedicated academic manager for top results.",
        "order": 3,
        "features": "Unlimited active tasks\nDedicated manager\nPriority phone support\n12-hour turnaround\nFull analytics dashboard\nUnlimited revisions\nPlagiarism reports",
        "prices": {
            "month": "79.99",
            "year": "799.99",
        },
    },
]


class Command(BaseCommand):
    help = "Seed default subscription plans (Essential, Pro, Expert) with monthly and yearly prices."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete all existing plans before seeding.",
        )

    def handle(self, *args, **options):
        if options["reset"]:
            count, _ = SubscriptionPrice.objects.all().delete()
            self.stdout.write(self.style.WARNING(f"Deleted {count} prices."))
            count, _ = Subscription.objects.all().delete()
            self.stdout.write(self.style.WARNING(f"Deleted {count} plans."))

        for plan_data in PLANS:
            sub, created = Subscription.objects.get_or_create(
                name=plan_data["name"],
                defaults={
                    "subtitle": plan_data["subtitle"],
                    "order": plan_data["order"],
                    "features": plan_data["features"],
                    "active": True,
                    "featured": True,
                },
            )
            verb = "Created" if created else "Already exists"
            self.stdout.write(f"  {verb}: {sub.name}")

            for interval, price_val in plan_data["prices"].items():
                sp, sp_created = SubscriptionPrice.objects.get_or_create(
                    subscription=sub,
                    interval=interval,
                    defaults={
                        "price": price_val,
                        "featured": True,
                        "order": plan_data["order"],
                    },
                )
                sp_verb = "Created" if sp_created else "Already exists"
                self.stdout.write(f"    {sp_verb}: ${price_val}/{interval}")

        self.stdout.write(self.style.SUCCESS("\nDone! Plans are ready."))
        self.stdout.write("Visit /pricing/ to see them, or the Django admin to manage them.")
