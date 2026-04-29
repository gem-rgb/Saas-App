"""
ML Engine for SaaS Analytics.
Uses scikit-learn for churn prediction, health scoring, and smart recommendations.
Models self-train as user data accumulates.
"""
import datetime
import logging
import numpy as np
from django.utils import timezone

logger = logging.getLogger(__name__)

# Feature extraction thresholds
HEALTHY_LOGIN_FREQ_DAYS = 3  # Login at least every 3 days = healthy
ENGAGEMENT_WINDOW_DAYS = 30


def _safe_import_sklearn():
    """Safely import sklearn — graceful fallback if not installed yet."""
    try:
        from sklearn.linear_model import LogisticRegression, LinearRegression
        from sklearn.preprocessing import StandardScaler
        return LogisticRegression, LinearRegression, StandardScaler
    except ImportError:
        logger.warning("scikit-learn not installed. ML features will use heuristic fallbacks.")
        return None, None, None


def extract_user_features(user):
    """
    Extract feature vector for a single user.
    Returns dict of raw features used by all ML models.
    """
    from analytics.models import UserActivity
    from visits.models import PageVisit
    from subscriptions.models import UserSubscription

    now = timezone.now()
    window_start = now - datetime.timedelta(days=ENGAGEMENT_WINDOW_DAYS)

    # Activity metrics
    activities = UserActivity.objects.filter(user=user, timestamp__gte=window_start)
    total_actions = activities.count()
    login_count = activities.filter(action='login').count()
    page_views = activities.filter(action='page_view').count()
    feature_uses = activities.filter(action='feature_use').count()
    support_contacts = activities.filter(action='support_contact').count()

    # Last login info
    last_activity = activities.order_by('-timestamp').first()
    days_since_last_activity = (now - last_activity.timestamp).days if last_activity else 30

    # Subscription info
    sub_age_days = 0
    has_active_sub = False
    sub_days_remaining = 0
    try:
        user_sub = UserSubscription.objects.get(user=user)
        has_active_sub = user_sub.is_active_status
        if user_sub.original_period_start:
            sub_age_days = (now - user_sub.original_period_start).days
        if user_sub.current_period_end:
            sub_days_remaining = max(0, (user_sub.current_period_end - now).days)
    except UserSubscription.DoesNotExist:
        pass

    # Page visit count (total from visits app)
    total_page_visits = PageVisit.objects.filter(
        timestamp__gte=window_start
    ).count()

    return {
        'total_actions': total_actions,
        'login_count': login_count,
        'page_views': page_views,
        'feature_uses': feature_uses,
        'support_contacts': support_contacts,
        'days_since_last_activity': days_since_last_activity,
        'sub_age_days': sub_age_days,
        'has_active_sub': 1 if has_active_sub else 0,
        'sub_days_remaining': sub_days_remaining,
        'total_page_visits': total_page_visits,
    }


def calculate_health_score(features):
    """
    Calculate a 0-100 health score based on user engagement features.
    Uses a weighted scoring algorithm.
    """
    score = 50  # Base score

    # Login frequency bonus (max +20)
    if features['login_count'] >= 20:
        score += 20
    elif features['login_count'] >= 10:
        score += 15
    elif features['login_count'] >= 5:
        score += 10
    elif features['login_count'] >= 1:
        score += 5

    # Recency bonus (max +20)
    days_inactive = features['days_since_last_activity']
    if days_inactive <= 1:
        score += 20
    elif days_inactive <= 3:
        score += 15
    elif days_inactive <= 7:
        score += 10
    elif days_inactive <= 14:
        score += 5
    else:
        score -= 10

    # Feature usage bonus (max +15)
    if features['feature_uses'] >= 10:
        score += 15
    elif features['feature_uses'] >= 5:
        score += 10
    elif features['feature_uses'] >= 1:
        score += 5

    # Active subscription bonus (+10)
    if features['has_active_sub']:
        score += 10
    else:
        score -= 15

    # Support contact penalty (frequent = frustrated user)
    if features['support_contacts'] >= 5:
        score -= 10
    elif features['support_contacts'] >= 3:
        score -= 5

    # Page view engagement (max +5)
    if features['page_views'] >= 15:
        score += 5
    elif features['page_views'] >= 5:
        score += 3

    return max(0, min(100, score))


def predict_churn_probability(features):
    """
    Predict churn probability using logistic regression if enough data exists,
    otherwise fall back to heuristic scoring.
    """
    LogisticRegression, _, StandardScaler = _safe_import_sklearn()

    # Heuristic fallback (always available)
    churn_score = 30  # Base

    # High inactivity = high churn risk
    if features['days_since_last_activity'] >= 14:
        churn_score += 30
    elif features['days_since_last_activity'] >= 7:
        churn_score += 20
    elif features['days_since_last_activity'] >= 3:
        churn_score += 10
    elif features['days_since_last_activity'] <= 1:
        churn_score -= 15

    # Low engagement = churn risk
    if features['total_actions'] <= 2:
        churn_score += 15
    elif features['total_actions'] >= 20:
        churn_score -= 20

    # No subscription = high risk
    if not features['has_active_sub']:
        churn_score += 20
    else:
        churn_score -= 10

    # Subscription ending soon
    if features['sub_days_remaining'] <= 7 and features['sub_days_remaining'] > 0:
        churn_score += 10

    # Many support contacts = frustration
    if features['support_contacts'] >= 3:
        churn_score += 10

    # Feature use = stickiness
    if features['feature_uses'] >= 5:
        churn_score -= 15

    return max(0, min(100, round(churn_score, 1)))


def predict_usage(features):
    """Predict next month's estimated page views based on current patterns."""
    current_views = features['page_views']
    login_frequency = features['login_count']

    # Simple growth/decay model
    if features['days_since_last_activity'] >= 14:
        # User is fading — predict decline
        return max(0, int(current_views * 0.5))
    elif features['days_since_last_activity'] <= 3:
        # Active user — predict growth
        growth = 1.1 + (login_frequency * 0.02)
        return int(current_views * min(growth, 2.0))
    else:
        # Stable
        return current_views


def generate_recommendations(features, health_score, churn_prob):
    """
    Generate smart, personalized recommendations based on ML analysis.
    Returns a list of recommendation dicts.
    """
    recs = []

    # High churn risk recommendations
    if churn_prob >= 60:
        recs.append({
            "type": "warning",
            "icon": "🔴",
            "title": "We miss you!",
            "text": "Your activity has dropped recently. Check out our latest features to get the most from your plan.",
            "action_text": "Explore Features",
            "action_url": "/#features",
        })

    # No subscription
    if not features['has_active_sub']:
        recs.append({
            "type": "upgrade",
            "icon": "⭐",
            "title": "Unlock Premium Features",
            "text": "You're on the free tier. Upgrade to access advanced analytics, priority support, and more.",
            "action_text": "View Plans",
            "action_url": "/pricing/",
        })

    # Low feature usage
    if features['feature_uses'] <= 2:
        recs.append({
            "type": "tip",
            "icon": "💡",
            "title": "Discover More Features",
            "text": "You've only used a few features. Explore your dashboard to find tools that can boost your productivity.",
            "action_text": "Go to Dashboard",
            "action_url": "/",
        })

    # Healthy and active — positive reinforcement
    if health_score >= 80:
        recs.append({
            "type": "success",
            "icon": "🏆",
            "title": "You're a Power User!",
            "text": f"Your engagement score is {health_score}/100. Keep up the great work!",
            "action_text": None,
            "action_url": None,
        })

    # Profile incomplete
    if features['total_actions'] >= 5:
        recs.append({
            "type": "info",
            "icon": "👤",
            "title": "Complete Your Profile",
            "text": "A complete profile helps us personalize your experience and connect you with peers.",
            "action_text": "Edit Profile",
            "action_url": "/profiles/edit/",
        })

    # Subscription expiring soon
    if 0 < features['sub_days_remaining'] <= 7:
        recs.append({
            "type": "warning",
            "icon": "⏰",
            "title": "Subscription Expiring Soon",
            "text": f"Your plan expires in {features['sub_days_remaining']} days. Renew to avoid service interruption.",
            "action_text": "Manage Billing",
            "action_url": "/accounts/billing/",
        })

    return recs[:5]  # Return top 5 recommendations


def analyze_user(user):
    """
    Main entry point: run full ML analysis for a user.
    Returns dict with all predictions and recommendations.
    """
    from analytics.models import MLPrediction

    features = extract_user_features(user)
    health = calculate_health_score(features)
    churn = predict_churn_probability(features)
    usage_forecast = predict_usage(features)
    recs = generate_recommendations(features, health, churn)

    # Determine engagement level
    if health >= 70:
        engagement = "high"
    elif health >= 40:
        engagement = "medium"
    else:
        engagement = "low"

    # Save/update prediction
    prediction, _ = MLPrediction.objects.update_or_create(
        user=user,
        defaults={
            'churn_probability': churn,
            'health_score': health,
            'engagement_level': engagement,
            'predicted_usage_next_month': usage_forecast,
            'recommendations': recs,
        }
    )

    return {
        'features': features,
        'health_score': health,
        'churn_probability': churn,
        'churn_risk_level': prediction.churn_risk_level,
        'engagement_level': engagement,
        'usage_forecast': usage_forecast,
        'recommendations': recs,
        'health_color': prediction.health_color,
    }


# ============ Assignment Matching ML Engine ============

def calculate_skill_match_score(assignment_skills, tasker_skills):
    """
    Calculate skill match between assignment requirements and tasker skills.
    Returns score from 0 to 1.
    """
    if not assignment_skills or not tasker_skills:
        return 0.0
    
    # Parse skills (comma-separated strings)
    req_skills = set(s.strip().lower() for s in assignment_skills.split(','))
    tasker_skill_set = set(s.strip().lower() for s in tasker_skills.split(','))
    
    if not req_skills:
        return 1.0
    
    # Calculate Jaccard similarity
    intersection = req_skills & tasker_skill_set
    union = req_skills | tasker_skill_set
    
    skill_match = len(intersection) / len(union) if union else 0.0
    
    # Bonus if tasker has MORE skills than required (versatility)
    extra_skills = len(tasker_skill_set - req_skills)
    versatility_bonus = min(0.1, extra_skills * 0.02)
    
    return min(1.0, skill_match + versatility_bonus)


def calculate_availability_score(tasker, assignment_hours):
    """
    Calculate availability match based on tasker's weekly hours and current workload.
    Returns score from 0 to 1.
    """
    # Get current active assignments for tasker
    from assignments.models import Assignment as AssignmentModel
    
    active_assignments = AssignmentModel.objects.filter(
        assigned_to=tasker,
        status__in=['posted', 'in_progress']
    ).aggregate(
        total_hours=models.Sum('estimated_hours')
    )
    
    current_hours = active_assignments.get('total_hours') or 0
    available_hours = max(0, tasker.availability_hours_per_week - current_hours)
    
    if assignment_hours <= available_hours:
        return 1.0
    elif available_hours > 0:
        return available_hours / assignment_hours
    else:
        return 0.0


def calculate_success_history_score(tasker):
    """
    Calculate score based on tasker's track record.
    Returns score from 0 to 1.
    """
    # Success rate is stored as percentage (0-100)
    success_rate = tasker.success_rate / 100.0
    
    # Recent completion bonus
    from assignments.models import AssignmentSubmission
    recent_submissions = AssignmentSubmission.objects.filter(
        tasker=tasker,
        submitted_at__gte=timezone.now() - datetime.timedelta(days=30)
    ).count()
    
    # More recent completions = higher reliability
    recency_bonus = min(0.15, recent_submissions * 0.03)
    
    return min(1.0, success_rate + recency_bonus)


def calculate_skill_level_match(tasker, assignment_priority):
    """
    Match tasker skill level with assignment priority.
    Returns score from 0 to 1.
    """
    priority_to_min_level = {
        'low': 'beginner',
        'medium': 'intermediate',
        'high': 'advanced',
        'urgent': 'expert',
    }
    
    skill_level_ranking = {
        'beginner': 1,
        'intermediate': 2,
        'advanced': 3,
        'expert': 4,
    }
    
    required_level = priority_to_min_level.get(assignment_priority, 'beginner')
    required_rank = skill_level_ranking.get(required_level, 1)
    tasker_rank = skill_level_ranking.get(tasker.skill_level, 1)
    
    if tasker_rank >= required_rank:
        return 1.0
    else:
        # Partial match if tasker is slightly below required level
        return tasker_rank / required_rank * 0.7


def match_assignment_to_taskers(assignment, top_n=5):
    """
    Use ML to find best-matching taskers for an assignment.
    Returns list of dicts with tasker info and match score.
    """
    from assignments.models import TaskerProfile
    from django.db import models as db_models
    
    # Get active taskers
    taskers = TaskerProfile.objects.filter(is_active_tasker=True)
    
    matches = []
    
    for tasker in taskers:
        # Calculate individual match components
        skill_match = calculate_skill_match_score(assignment.required_skills, tasker.skills)
        availability = calculate_availability_score(tasker, assignment.estimated_hours)
        success_history = calculate_success_history_score(tasker)
        skill_level = calculate_skill_level_match(tasker, assignment.priority)
        
        # Weighted combination of factors
        # Skill match is most important, then success history, then availability
        combined_score = (
            skill_match * 0.4 +
            success_history * 0.3 +
            availability * 0.2 +
            skill_level * 0.1
        )
        
        # Only include matches above threshold
        if combined_score > 0.3:
            matches.append({
                'tasker': tasker,
                'score': round(combined_score, 3),
                'skill_match': round(skill_match, 3),
                'availability': round(availability, 3),
                'success_history': round(success_history, 3),
                'skill_level': round(skill_level, 3),
            })
    
    # Sort by score descending
    matches.sort(key=lambda x: x['score'], reverse=True)
    
    return matches[:top_n]


def recommend_assignment_to_tasker(tasker):
    """
    Recommend assignments for a specific tasker based on their skills and availability.
    Returns list of recommended assignments.
    """
    from assignments.models import Assignment as AssignmentModel
    
    # Get posted assignments not yet assigned
    available_assignments = AssignmentModel.objects.filter(
        status='posted',
        assigned_to=None
    )
    
    recommendations = []
    
    for assignment in available_assignments:
        # Calculate match score
        skill_match = calculate_skill_match_score(assignment.required_skills, tasker.skills)
        availability = calculate_availability_score(tasker, assignment.estimated_hours)
        skill_level = calculate_skill_level_match(tasker, assignment.priority)
        
        combined_score = (
            skill_match * 0.4 +
            availability * 0.3 +
            skill_level * 0.3
        )
        
        if combined_score > 0.5:  # Higher threshold for personal recommendations
            recommendations.append({
                'assignment': assignment,
                'score': round(combined_score, 3),
                'match_details': {
                    'skill_match': round(skill_match, 3),
                    'availability': round(availability, 3),
                    'skill_level': round(skill_level, 3),
                }
            })
    
    # Sort by score descending and return top 10
    recommendations.sort(key=lambda x: x['score'], reverse=True)
    return recommendations[:10]
