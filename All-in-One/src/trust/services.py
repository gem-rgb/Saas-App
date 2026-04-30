from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from agents.document_verification import verify_document_bundle
from agents.fraud_detection import assess_application_risk
from agents.interview_agent import infer_interview_focus, run_interview_session
from agents.gemini_interview import GeminiInterviewAgent, INTERVIEW_FIELDS
from trust.models import (
    AIInterviewScore,
    AIInterviewSession,
    IdentityVerification,
    TaskerApplication,
    InteractiveInterviewSession,
    InterviewQuestion,
)


def evaluate_application(application):
    document_result = verify_document_bundle(application)
    risk_result = assess_application_risk(application, document_result=document_result)

    application.document_confidence = document_result["authenticity_confidence"]
    application.competency_confidence = document_result["competency_confidence"]
    application.fraud_risk_score = risk_result["risk_score"]
    application.manual_review_required = risk_result["manual_review_required"]
    application.trust_score = risk_result["trust_score"]
    application.decision_reason = risk_result["summary"]
    application.save(
        update_fields=[
            "document_confidence",
            "competency_confidence",
            "fraud_risk_score",
            "manual_review_required",
            "trust_score",
            "decision_reason",
            "updated_at",
        ]
    )

    identity, _ = IdentityVerification.objects.get_or_create(application=application)
    identity.authenticity_score = document_result["authenticity_confidence"]
    identity.document_match_score = document_result["document_match_score"]
    identity.face_match_score = document_result["face_match_score"]
    identity.liveness_score = document_result["liveness_score"]
    identity.review_notes = document_result["summary"]
    identity.status = IdentityVerification.Status.UNDER_REVIEW if risk_result["manual_review_required"] else IdentityVerification.Status.APPROVED
    if not risk_result["manual_review_required"]:
        identity.verified_at = timezone.now()
    identity.save()

    return {
        "document_result": document_result,
        "risk_result": risk_result,
        "identity": identity,
    }


@transaction.atomic
def run_ai_interview(application):
    interview_payload = run_interview_session(application)
    session = AIInterviewSession.objects.create(
        application=application,
        mode=interview_payload["mode"],
        transcript=interview_payload["transcript"],
        transcript_text=interview_payload["transcript_text"],
        technical_score=interview_payload["technical_score"],
        writing_score=interview_payload["writing_score"],
        behavioral_score=interview_payload["behavioral_score"],
        overall_score=interview_payload["overall_score"],
        recommendation=interview_payload["recommendation"],
        ranking_percentile=interview_payload["ranking_percentile"],
        interviewer_version=interview_payload["interviewer_version"],
        ended_at=timezone.now(),
        metadata=interview_payload.get("metadata", {}),
    )

    for item in interview_payload.get("scores", []):
        if item.get("competency_area") is None:
            continue
        AIInterviewScore.objects.create(
            session=session,
            competency_area=item["competency_area"],
            score=item["score"],
            evidence=item.get("evidence", ""),
            notes=item.get("notes", ""),
        )

    application.interview_confidence = session.overall_score
    application.save(update_fields=["interview_confidence", "updated_at"])
    return session


def score_application(application):
    base = 40.0
    base += application.document_confidence * 0.25
    base += application.competency_confidence * 0.25
    base += application.interview_confidence * 0.30
    base += application.trust_score * 0.20
    base -= application.fraud_risk_score * 0.18
    return max(0.0, min(100.0, round(base, 2)))


def is_tasker_ready(application):
    if application.status == TaskerApplication.Status.APPROVED:
        return True
    ready_states = {
        TaskerApplication.Status.SUBMITTED,
        TaskerApplication.Status.UNDER_REVIEW,
        TaskerApplication.Status.DOCUMENT_REVIEW,
        TaskerApplication.Status.INTERVIEW_PENDING,
    }
    return application.status in ready_states and score_application(application) >= 70


# Interactive Interview Services with Gemini

def _resolve_interview_context(application, field: str | None = None):
    focus = infer_interview_focus(application)
    selected_field = (field or "").strip()
    if selected_field not in INTERVIEW_FIELDS:
        selected_field = focus["field"]
    if selected_field not in INTERVIEW_FIELDS:
        selected_field = InteractiveInterviewSession.InterviewField.GENERAL_KNOWLEDGE
    return selected_field, focus


def _session_focus_topic(session):
    metadata = session.metadata or {}
    topic = metadata.get("focus_topic")
    if topic:
        return topic
    return infer_interview_focus(session.application)["topic"]


def create_interactive_interview_session(application, difficulty: str, field: str | None = None, language: str = None):
    """Create a new interactive interview session"""
    selected_field, focus = _resolve_interview_context(application, field)
    
    session = InteractiveInterviewSession.objects.create(
        application=application,
        field=selected_field,
        difficulty=difficulty,
        language=language or "",
        status=InteractiveInterviewSession.Status.PENDING,
        metadata={
            "focus_field": selected_field,
            "focus_topic": focus["topic"],
            "competency_names": focus["competency_names"],
            "competency_slugs": focus["competency_slugs"],
            "inferred_field": focus["field"],
            "requested_field": field or "",
        },
    )
    return session


@transaction.atomic
def start_interactive_interview(session_id: int):
    """Start an interactive interview and generate first question"""
    session = InteractiveInterviewSession.objects.get(id=session_id)
    
    if session.status != InteractiveInterviewSession.Status.PENDING:
        raise ValueError("Interview already started or completed")
    
    session.status = InteractiveInterviewSession.Status.IN_PROGRESS
    session.started_at = timezone.now()
    session.save(update_fields=["status", "started_at"])
    
    # Initialize Gemini agent
    topic = _session_focus_topic(session)
    agent = GeminiInterviewAgent(
        field=session.field,
        difficulty=session.difficulty,
        language=session.language if session.language else None,
        topic=topic,
    )
    
    # Generate first question
    question_data = agent.generate_question(question_number=1)
    
    # Create question record
    question = InterviewQuestion.objects.create(
        session=session,
        question_number=1,
        question_text=question_data.get("question", ""),
        expected_concepts=question_data.get("expected_concepts", []),
        ideal_answer_points=question_data.get("ideal_answer_points", []),
        time_limit_minutes=question_data.get("time_limit_minutes", 3),
    )
    
    # Store agent state in session metadata
    metadata = session.metadata or {}
    metadata.update(
        {
            "agent_initialized": True,
            "current_question_id": question.id,
            "scores": metadata.get("scores", []),
            "focus_topic": topic,
        }
    )
    session.metadata = metadata
    session.save(update_fields=["metadata"])
    
    return {
        "session": session,
        "question": question,
        "question_data": question_data,
    }


@transaction.atomic
def submit_interview_answer(session_id: int, question_number: int, user_answer: str):
    """Submit answer for current question and get verification"""
    session = InteractiveInterviewSession.objects.get(id=session_id)
    
    if session.status != InteractiveInterviewSession.Status.IN_PROGRESS:
        raise ValueError("Interview is not in progress")
    
    # Get the question
    question = InterviewQuestion.objects.get(session=session, question_number=question_number)
    
    if question.user_answer:
        raise ValueError("This question has already been answered")
    
    # Update question with answer
    question.user_answer = user_answer
    question.answered_at = timezone.now()
    question.save(update_fields=["user_answer", "answered_at"])
    
    # Verify answer using Gemini
    topic = _session_focus_topic(session)
    agent = GeminiInterviewAgent(
        field=session.field,
        difficulty=session.difficulty,
        language=session.language if session.language else None,
        topic=topic,
    )
    
    evaluation = agent.verify_answer(question.question_text, user_answer)
    
    # Store evaluation
    question.is_correct = evaluation.get("is_correct", False)
    question.correctness_score = evaluation.get("correctness_score", 0)
    question.explanation = evaluation.get("explanation", "")
    question.strengths = evaluation.get("strengths", [])
    question.weaknesses = evaluation.get("weaknesses", [])
    question.feedback = evaluation.get("feedback", "")
    question.evaluated_at = timezone.now()
    question.save(update_fields=[
        "is_correct",
        "correctness_score",
        "explanation",
        "strengths",
        "weaknesses",
        "feedback",
        "evaluated_at",
    ])
    
    # Update session scores
    session.questions_completed += 1
    metadata = session.metadata or {}
    scores = metadata.get("scores", [])
    scores.append(evaluation.get("correctness_score", 0))
    metadata["scores"] = scores
    session.metadata = metadata
    
    # Check if interview should continue
    should_proceed = evaluation.get("should_proceed", True) and session.questions_completed < session.total_questions
    
    return {
        "evaluation": evaluation,
        "question": question,
        "session_progress": {
            "current_question": session.questions_completed,
            "total_questions": session.total_questions,
            "should_proceed": should_proceed,
        }
    }


@transaction.atomic
def get_next_interview_question(session_id: int):
    """Generate and return the next interview question"""
    session = InteractiveInterviewSession.objects.get(id=session_id)
    
    if session.status != InteractiveInterviewSession.Status.IN_PROGRESS:
        raise ValueError("Interview is not in progress")
    
    # Check if interview is complete
    if session.questions_completed >= session.total_questions:
        return complete_interview(session_id)
    
    # Generate next question
    topic = _session_focus_topic(session)
    agent = GeminiInterviewAgent(
        field=session.field,
        difficulty=session.difficulty,
        language=session.language if session.language else None,
        topic=topic,
    )
    
    next_question_number = session.questions_completed + 1
    question_data = agent.generate_question(question_number=next_question_number)
    
    # Create question record
    question = InterviewQuestion.objects.create(
        session=session,
        question_number=next_question_number,
        question_text=question_data.get("question", ""),
        expected_concepts=question_data.get("expected_concepts", []),
        ideal_answer_points=question_data.get("ideal_answer_points", []),
        time_limit_minutes=question_data.get("time_limit_minutes", 3),
    )
    
    # Update session metadata
    metadata = session.metadata or {}
    metadata["current_question_id"] = question.id
    metadata["focus_topic"] = topic
    session.metadata = metadata
    session.save(update_fields=["metadata"])
    
    return {
        "question": question,
        "question_data": question_data,
        "progress": {
            "current_question": next_question_number,
            "total_questions": session.total_questions,
        }
    }


@transaction.atomic
def complete_interview(session_id: int):
    """Complete interview and calculate final scores"""
    session = InteractiveInterviewSession.objects.get(id=session_id)
    
    # Get all questions and scores
    questions = session.questions.all().order_by("question_number")
    scores = [q.correctness_score for q in questions if q.evaluated_at]
    
    if not scores:
        overall_score = 0.0
        recommendation = "incomplete"
        percentile = 0.0
    else:
        overall_score = sum(scores) / len(scores)
        
        # Recommendation logic
        if overall_score >= 85:
            recommendation = "strong_hire"
            percentile = 90.0
        elif overall_score >= 70:
            recommendation = "hire"
            percentile = 75.0
        elif overall_score >= 55:
            recommendation = "hold"
            percentile = 50.0
        else:
            recommendation = "reject"
            percentile = 20.0
    
    # Update session
    session.status = InteractiveInterviewSession.Status.COMPLETED
    session.overall_score = round(overall_score, 2)
    session.recommendation = recommendation
    session.percentile = percentile
    session.completed_at = timezone.now()
    
    # Build transcript for reference
    transcript = []
    for q in questions:
        transcript.append({
            "speaker": "agent",
            "message": q.question_text,
            "question_number": q.question_number,
        })
        if q.user_answer:
            transcript.append({
                "speaker": "candidate",
                "message": q.user_answer,
                "score": q.correctness_score,
            })
    
    metadata = session.metadata or {}
    metadata.update(
        {
            "scores": scores,
            "transcript": transcript,
            "average_score": round(overall_score, 2),
        }
    )
    session.metadata = metadata
    session.save(update_fields=[
        "status",
        "overall_score",
        "recommendation",
        "percentile",
        "completed_at",
        "metadata",
    ])
    
    # Update application's interview confidence
    application = session.application
    application.interview_confidence = overall_score
    application.save(update_fields=["interview_confidence", "updated_at"])
    
    return {
        "session": session,
        "final_score": overall_score,
        "recommendation": recommendation,
        "percentile": percentile,
        "total_questions": questions.count(),
        "transcript": transcript,
    }


def get_interview_progress(session_id: int):
    """Get current interview progress and stats"""
    session = InteractiveInterviewSession.objects.get(id=session_id)
    questions = session.questions.all()
    scores = [q.correctness_score for q in questions if q.evaluated_at]
    
    return {
        "session_id": session.id,
        "status": session.status,
        "field": session.get_field_display(),
        "difficulty": session.difficulty,
        "current_question": session.questions_completed,
        "total_questions": session.total_questions,
        "progress_percentage": round((session.questions_completed / session.total_questions) * 100, 1),
        "current_average_score": round(sum(scores) / len(scores), 2) if scores else 0.0,
        "scores": scores,
    }
