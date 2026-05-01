from rest_framework import serializers

from assignments.models import TaskerProfile
from marketplace.models import (
    TaskAttachment,
    TaskAuditEvent,
    TaskCategory,
    TaskMatchSuggestion,
    TaskNotification,
    TaskOrder,
    TaskPayment,
    TaskPremiumSession,
    TaskRating,
    TaskRevisionRequest,
    TaskStatusEvent,
    TaskSubmission,
)


class TaskCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskCategory
        fields = ["id", "name", "slug", "description", "icon", "active", "order"]


class TaskerMiniSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    display_name = serializers.CharField(source="user.get_full_name", read_only=True)

    class Meta:
        model = TaskerProfile
        fields = [
            "id",
            "username",
            "display_name",
            "skill_level",
            "skills",
            "trust_score",
            "quality_score",
            "on_time_delivery_rate",
            "reliability_score",
            "kyc_status",
            "competency_status",
            "interview_status",
            "admin_approved",
        ]


class TaskAttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskAttachment
        fields = ["id", "file", "file_kind", "description", "uploaded_by", "uploaded_at", "file_size_mb"]


class TaskMatchSuggestionSerializer(serializers.ModelSerializer):
    tasker = TaskerMiniSerializer(read_only=True)

    class Meta:
        model = TaskMatchSuggestion
        fields = [
            "id",
            "tasker",
            "score",
            "confidence",
            "ranking_position",
            "state",
            "rationale",
            "selected_by",
            "is_primary",
            "created_at",
        ]


class TaskStatusEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskStatusEvent
        fields = ["id", "previous_status", "new_status", "actor_role", "note", "payload", "created_at"]


class TaskSubmissionSerializer(serializers.ModelSerializer):
    tasker = TaskerMiniSerializer(read_only=True)

    class Meta:
        model = TaskSubmission
        fields = [
            "id",
            "tasker",
            "version",
            "status",
            "submission_text",
            "file",
            "summary",
            "quality_score",
            "ai_quality_score",
            "student_feedback",
            "reviewer_notes",
            "submitted_at",
            "reviewed_at",
        ]


class TaskRevisionRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskRevisionRequest
        fields = ["id", "reason", "status", "due_at", "resolved_at", "resolution_notes", "created_at"]


class TaskPremiumSessionSerializer(serializers.ModelSerializer):
    tasker = TaskerMiniSerializer(read_only=True)
    display_fee_label = serializers.ReadOnlyField()
    checkout_url = serializers.ReadOnlyField()

    class Meta:
        model = TaskPremiumSession
        fields = [
            "id",
            "tasker",
            "session_type",
            "topic",
            "scheduled_for",
            "duration_minutes",
            "extra_fee_cents",
            "currency",
            "display_fee_label",
            "status",
            "student_notes",
            "tasker_notes",
            "provider_reference",
            "accepted_at",
            "paid_at",
            "completed_at",
            "declined_at",
            "cancelled_at",
            "checkout_url",
            "metadata",
            "created_at",
            "updated_at",
        ]


class TaskRatingSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskRating
        fields = [
            "id",
            "overall_rating",
            "accuracy_rating",
            "communication_rating",
            "speed_rating",
            "comments",
            "created_at",
        ]


class TaskPaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskPayment
        fields = [
            "id",
            "payment_kind",
            "amount_cents",
            "currency",
            "provider",
            "provider_reference",
            "status",
            "escrow_status",
            "paid_at",
            "released_at",
            "refunded_at",
            "created_at",
        ]


class TaskNotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskNotification
        fields = ["id", "channel", "title", "body", "is_read", "sent_at", "created_at"]


class TaskAuditEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskAuditEvent
        fields = ["id", "actor_role", "entity_type", "entity_id", "event_type", "payload", "created_at"]


class TaskOrderSerializer(serializers.ModelSerializer):
    category = TaskCategorySerializer(read_only=True)
    assigned_tasker = TaskerMiniSerializer(read_only=True)
    attachments = TaskAttachmentSerializer(many=True, read_only=True)
    match_suggestions = TaskMatchSuggestionSerializer(many=True, read_only=True)
    submissions = TaskSubmissionSerializer(many=True, read_only=True)
    premium_sessions = TaskPremiumSessionSerializer(many=True, read_only=True)
    status_events = TaskStatusEventSerializer(many=True, read_only=True)
    ratings = TaskRatingSerializer(many=True, read_only=True)
    payments = TaskPaymentSerializer(many=True, read_only=True)
    notifications = TaskNotificationSerializer(many=True, read_only=True)
    audit_events = TaskAuditEventSerializer(many=True, read_only=True)
    effective_budget_cents = serializers.SerializerMethodField()
    display_price_label = serializers.SerializerMethodField()
    price_source_label = serializers.SerializerMethodField()
    estimated_price_cents = serializers.SerializerMethodField()

    class Meta:
        model = TaskOrder
        fields = [
            "id",
            "student",
            "title",
            "subject",
            "category",
            "competency_area",
            "description",
            "instructions",
            "deadline",
            "estimated_hours",
            "budget_cents",
            "pricing_suggestion_cents",
            "effective_budget_cents",
            "display_price_label",
            "price_source_label",
            "estimated_price_cents",
            "currency",
            "complexity_level",
            "status",
            "assigned_tasker",
            "region_preference",
            "required_trust_score",
            "deadline_feasibility_score",
            "assignment_confidence",
            "quality_score",
            "revision_count",
            "platform_fee_cents",
            "payment_status",
            "published_at",
            "assigned_at",
            "completed_at",
            "cancelled_at",
            "ai_estimate",
            "metadata",
            "attachments",
            "match_suggestions",
            "submissions",
            "status_events",
            "premium_sessions",
            "ratings",
            "payments",
            "notifications",
            "audit_events",
            "created_at",
            "updated_at",
        ]

    def get_effective_budget_cents(self, obj):
        return obj.effective_budget_cents

    def get_display_price_label(self, obj):
        return obj.display_price_label

    def get_price_source_label(self, obj):
        return obj.price_source_label

    def get_estimated_price_cents(self, obj):
        return obj.pricing_suggestion_cents or obj.effective_budget_cents
