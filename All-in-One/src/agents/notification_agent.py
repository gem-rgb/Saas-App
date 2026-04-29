from __future__ import annotations


def build_notifications(event_type, recipient_name, context=None):
    context = context or {}
    if event_type == "deadline_reminder":
        return {
            "title": "Deadline reminder",
            "body": f"{recipient_name}, your task is due soon. {context.get('task_title', 'Please review the queue.')}",
        }
    if event_type == "escalation_notice":
        return {
            "title": "Escalation notice",
            "body": f"{recipient_name}, a task needs attention in the regional queue.",
        }
    if event_type == "payment_release":
        return {
            "title": "Payment released",
            "body": f"{recipient_name}, a payment has been released for a completed task.",
        }
    return {
        "title": "Marketplace update",
        "body": f"{recipient_name}, there is a new update in your workspace.",
    }

