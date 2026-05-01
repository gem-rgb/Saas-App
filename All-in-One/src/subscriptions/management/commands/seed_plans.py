"""
Management command to seed default subscription plans.
Usage: python manage.py seed_plans
"""
from decimal import Decimal

from django.core.management.base import BaseCommand

from subscriptions.models import Subscription, SubscriptionPrice


PLANS = [
    {
        "name": "Essential",
        "subtitle": "For students who need help with occasional assignments.",
        "order": 1,
        "features": "Up to 3 active tasks\nStandard matching\nEmail support\n48-hour turnaround\nBasic analytics",
        "feature_codes": [
            "active_tasks_3",
            "standard_matching",
            "email_support",
            "turnaround_48h",
            "basic_analytics",
        ],
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
        "feature_codes": [
            "active_tasks_10",
            "priority_matching",
            "live_chat_support",
            "turnaround_24h",
            "advanced_analytics",
            "revision_guarantee",
        ],
        "prices": {
            "month": "29.99",
            "year": "299.99",
        },
    },
    {
        "name": "Expert",
        "subtitle": "Unlimited access with premium exam sessions and priority support.",
        "order": 3,
        "features": "Unlimited active tasks\nPriority matching\nPriority phone support\n12-hour turnaround\nFull analytics dashboard\nUnlimited revisions\nPlagiarism reports\nPremium exam sessions",
        "feature_codes": [
            "active_tasks_unlimited",
            "priority_matching",
            "priority_phone_support",
            "turnaround_12h",
            "full_analytics_dashboard",
            "unlimited_revisions",
            "plagiarism_reports",
            "premium_sessions",
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
                changed_fields = []
                if sp.price != Decimal(price_val):
                    sp.price = Decimal(price_val)
                    changed_fields.append("price")
                if sp.order != plan_data["order"]:
                    sp.order = plan_data["order"]
                    changed_fields.append("order")
                if sp.featured is not True:
                    sp.featured = True
                    changed_fields.append("featured")
                if not sp.paystack_id:
                    sp.paystack_id = f"plan_local_{plan_data['name'].lower()}_{interval}"
                    changed_fields.append("paystack_id")
                if changed_fields:
                    sp.save(update_fields=changed_fields + ["updated"])
                sp_verb = "Created" if sp_created else "Already exists"
                self.stdout.write(f"    {sp_verb}: ${price_val}/{interval}")

        self.stdout.write(self.style.SUCCESS("\nDone! Plans are ready."))
        self.stdout.write("Visit /pricing/ to see them, or the Django admin to manage them.")
