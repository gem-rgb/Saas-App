"""
Management command to seed default subscription plans.
Usage: python manage.py seed_plans
"""
from django.core.management.base import BaseCommand

from subscriptions.models import Subscription, SubscriptionPrice


PLANS = [
    {
        "name": "Essential",
        "subtitle": "For students who want clean assignment support and subject-based writer suggestions.",
        "order": 1,
        "features": "Up to 3 active assignments\nSubject-based writer recommendations\nAssignment tracking\nEmail support\nBasic subscription access",
        "feature_codes": [
            "task_creation",
            "subject_recommendations",
            "task_tracking",
            "basic_support",
        ],
        "prices": {
            "month": "9.99",
            "year": "99.99",
        },
    },
    {
        "name": "Pro",
        "subtitle": "For students and taskers who need live routing, chat, and richer workflow controls.",
        "order": 2,
        "features": "Up to 10 active assignments\nLive marketplace access\nPriority matching\nIn-app task chat\nRevision requests\nAssignment analytics",
        "feature_codes": [
            "task_creation",
            "subject_recommendations",
            "live_marketplace",
            "priority_matching",
            "task_chat",
            "revision_requests",
            "analytics_dashboard",
        ],
        "prices": {
            "month": "29.99",
            "year": "299.99",
        },
    },
    {
        "name": "Expert",
        "subtitle": "For teams that need manager oversight, dispute handling, and premium reporting.",
        "order": 3,
        "features": "Unlimited active assignments\nDedicated manager console\nDispute resolution and refunds\nPriority support\nFull analytics dashboard\nPlagiarism and quality reports",
        "feature_codes": [
            "task_creation",
            "subject_recommendations",
            "live_marketplace",
            "manager_console",
            "dispute_resolution",
            "refund_management",
            "analytics_dashboard",
            "quality_reports",
        ],
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
                    "feature_codes": plan_data["feature_codes"],
                    "active": True,
                    "featured": True,
                    # Placeholder prevents save() from calling Paystack API when local IDs are enough.
                    "paystack_id": f"prod_local_{plan_data['name'].lower()}",
                },
            )

            updated_fields = []
            if sub.subtitle != plan_data["subtitle"]:
                sub.subtitle = plan_data["subtitle"]
                updated_fields.append("subtitle")
            if sub.order != plan_data["order"]:
                sub.order = plan_data["order"]
                updated_fields.append("order")
            if sub.features != plan_data["features"]:
                sub.features = plan_data["features"]
                updated_fields.append("features")
            if sub.feature_codes != plan_data["feature_codes"]:
                sub.feature_codes = plan_data["feature_codes"]
                updated_fields.append("feature_codes")
            if updated_fields:
                sub.save(update_fields=updated_fields + ["updated"])

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
                        "paystack_id": f"plan_local_{plan_data['name'].lower()}_{interval}",
                    },
                )
                sp_verb = "Created" if sp_created else "Already exists"
                self.stdout.write(f"    {sp_verb}: ${price_val}/{interval}")

        self.stdout.write(self.style.SUCCESS("\nDone! Plans are ready."))
        self.stdout.write("Visit /pricing/ to see them, or the Django admin to manage them.")
