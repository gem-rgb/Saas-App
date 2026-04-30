"""
Gemini-powered Interactive Interview Agent
Handles dynamic question generation, real-time answer verification, and scoring
"""
import json
import logging
from typing import Optional

from django.conf import settings

logger = logging.getLogger(__name__)

try:
    import google.generativeai as genai
except ImportError:  # pragma: no cover - optional dependency in this workspace
    genai = None

if genai and settings.GOOGLE_GEMINI_API_KEY:
    genai.configure(api_key=settings.GOOGLE_GEMINI_API_KEY)

# Interview field templates
INTERVIEW_FIELDS = {
    "software_engineering": {
        "name": "Software Engineering",
        "description": "Coding interviews for developers",
        "languages": ["Python", "JavaScript", "Java", "C++", "Go", "Rust"],
        "difficulty_levels": ["Beginner", "Intermediate", "Advanced"],
        "topic_count": 5,
    },
    "data_science": {
        "name": "Data Science",
        "description": "Data analysis and ML interviews",
        "languages": ["Python", "R", "SQL"],
        "difficulty_levels": ["Beginner", "Intermediate", "Advanced"],
        "topic_count": 5,
    },
    "chemistry": {
        "name": "Chemistry",
        "description": "Chemistry subject interviews",
        "languages": None,
        "difficulty_levels": ["High School", "Undergraduate", "Advanced"],
        "topic_count": 5,
    },
    "biology": {
        "name": "Biology",
        "description": "Biology subject interviews",
        "languages": None,
        "difficulty_levels": ["High School", "Undergraduate", "Advanced"],
        "topic_count": 5,
    },
    "mathematics": {
        "name": "Mathematics",
        "description": "Mathematics problem-solving",
        "languages": None,
        "difficulty_levels": ["High School", "Undergraduate", "Advanced"],
        "topic_count": 5,
    },
    "general_knowledge": {
        "name": "General Knowledge",
        "description": "General knowledge and aptitude",
        "languages": None,
        "difficulty_levels": ["Beginner", "Intermediate", "Advanced"],
        "topic_count": 5,
    },
}


class GeminiInterviewAgent:
    """Manages interactive interviews with Gemini"""

    def __init__(self, field: str, difficulty: str, language: Optional[str] = None, topic: Optional[str] = None):
        self.field = field
        self.difficulty = difficulty
        self.language = language
        self.topic = topic or ""
        self.field_config = INTERVIEW_FIELDS.get(field, {})
        self.use_gemini = bool(genai and settings.GOOGLE_GEMINI_API_KEY)
        self.model = genai.GenerativeModel("gemini-pro") if self.use_gemini else None
        self.conversation_history = []
        self.questions_asked = 0
        self.total_questions = self.field_config.get("topic_count", 5)
        self.scores = []

    def generate_question(self, question_number: Optional[int] = None) -> dict:
        """Generate the next interview question using Gemini"""
        question_index = question_number or (self.questions_asked + 1)
        subject_name = self.topic or self.field_config.get("name", self.field)
        if not self.use_gemini:
            self.questions_asked = question_index
            return {
                "question": f"Explain a core concept in {subject_name} at {self.difficulty.lower()} level.",
                "expected_concepts": ["core concepts", "problem solving"],
                "ideal_answer_points": ["clear explanation", "practical example", "correct terminology"],
                "time_limit_minutes": 3,
                "mode": "fallback",
            }

        try:
            field_name = self.field_config.get("name", self.field)

            prompt = f"""You are an expert interviewer for a tasker who selected proficiency in {subject_name}.
The interview category is {field_name} at difficulty level {self.difficulty}.

Generate a single, clear, and specific question for a technical/subject interview.
The question should:
- Be appropriate for {self.difficulty} level
- Be answerable in 2-3 minutes
- Test practical knowledge and problem-solving
- Be unambiguous and well-formulated"""

            if self.topic:
                prompt += f"\n- Keep the question anchored to {self.topic}."
            if self.language:
                prompt += f"\n- Be focused on {self.language} programming language"

            prompt += f"""

Question {question_index} of {self.total_questions}:

Respond in JSON format:
{{
    "question": "Your question here",
    "expected_concepts": ["concept1", "concept2", "concept3"],
    "ideal_answer_points": ["point1", "point2", "point3"],
    "time_limit_minutes": 3
}}"""

            response = self.model.generate_content(prompt)
            
            try:
                # Extract JSON from response
                response_text = response.text
                start_idx = response_text.find('{')
                end_idx = response_text.rfind('}') + 1
                json_str = response_text[start_idx:end_idx]
                question_data = json.loads(json_str)
            except (json.JSONDecodeError, ValueError):
                # Fallback if JSON parsing fails
                question_data = {
                    "question": response.text,
                    "expected_concepts": [],
                    "ideal_answer_points": [],
                    "time_limit_minutes": 3
                }

            self.questions_asked = question_index
            return question_data

        except Exception as e:
            logger.error(f"Error generating question: {e}")
            return {
                "question": f"Tell me about your experience in {subject_name}.",
                "expected_concepts": ["Experience", "Skills"],
                "ideal_answer_points": [],
                "time_limit_minutes": 3,
                "error": str(e)
            }

    def verify_answer(self, question: str, user_answer: str) -> dict:
        """Verify and score the user's answer using Gemini"""
        if not self.use_gemini:
            answer = (user_answer or "").strip()
            score = 45
            if len(answer) > 120:
                score += 20
            if any(term in answer.lower() for term in ["because", "example", "therefore", "step"]):
                score += 15
            if len(answer.split()) > 50:
                score += 10
            evaluation = {
                "is_correct": score >= 60,
                "correctness_score": min(100, score),
                "explanation": "Fallback evaluation completed without Gemini.",
                "strengths": [],
                "weaknesses": [],
                "feedback": "Expand your answer with concrete examples and clear reasoning.",
                "should_proceed": score >= 50,
                "mode": "fallback",
            }
            self.scores.append(evaluation.get("correctness_score", 0))
            return evaluation

        try:
            field_name = self.field_config.get("name", self.field)
            subject_name = self.topic or field_name

            prompt = f"""You are an expert evaluator for {subject_name} interviews at {self.difficulty} level.

Evaluate the following answer:

QUESTION: {question}

USER'S ANSWER: {user_answer}

Provide a detailed evaluation in JSON format:
{{
    "is_correct": true/false,
    "correctness_score": 0-100,
    "explanation": "Why this answer is correct/incorrect",
    "strengths": ["strength1", "strength2"],
    "weaknesses": ["weakness1", "weakness2"],
    "feedback": "Constructive feedback for improvement",
    "should_proceed": true/false
}}

Be fair but accurate. A score of 60+ means the answer demonstrates adequate understanding."""

            response = self.model.generate_content(prompt)
            
            try:
                response_text = response.text
                start_idx = response_text.find('{')
                end_idx = response_text.rfind('}') + 1
                json_str = response_text[start_idx:end_idx]
                evaluation = json.loads(json_str)
            except (json.JSONDecodeError, ValueError):
                evaluation = {
                    "is_correct": True,
                    "correctness_score": 75,
                    "explanation": response.text,
                    "strengths": [],
                    "weaknesses": [],
                    "feedback": "Keep learning and practicing.",
                    "should_proceed": True
                }

            # Store score
            self.scores.append(evaluation.get("correctness_score", 0))
            
            return evaluation

        except Exception as e:
            logger.error(f"Error verifying answer: {e}")
            return {
                "is_correct": True,
                "correctness_score": 50,
                "explanation": "Could not verify answer due to system error",
                "feedback": "Please try again",
                "should_proceed": True,
                "error": str(e)
            }

    def calculate_final_score(self) -> dict:
        """Calculate interview performance metrics"""
        if not self.scores:
            return {
                "overall_score": 0.0,
                "average_score": 0.0,
                "recommendation": "No questions answered",
            }

        average = sum(self.scores) / len(self.scores)
        
        # Recommendation logic
        if average >= 85:
            recommendation = "strong_hire"
            percentile = 90.0
        elif average >= 70:
            recommendation = "hire"
            percentile = 75.0
        elif average >= 55:
            recommendation = "hold"
            percentile = 50.0
        else:
            recommendation = "reject"
            percentile = 20.0

        return {
            "overall_score": round(average, 2),
            "average_score": round(average, 2),
            "total_questions": len(self.scores),
            "scores": self.scores,
            "recommendation": recommendation,
            "percentile": percentile,
        }

    def is_interview_complete(self) -> bool:
        """Check if interview is complete"""
        return self.questions_asked >= self.total_questions

    def get_interview_progress(self) -> dict:
        """Get current interview progress"""
        return {
            "current_question": self.questions_asked,
            "total_questions": self.total_questions,
            "progress_percentage": round((self.questions_asked / self.total_questions) * 100, 1),
            "current_average_score": round(sum(self.scores) / len(self.scores), 2) if self.scores else 0.0,
        }
