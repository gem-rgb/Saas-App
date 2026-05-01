from django.test import SimpleTestCase, override_settings

from agents.plagiarism_engine import build_plagiarism_check
from agents.verification_service import run_assignment_verification


class RubricVerificationTests(SimpleTestCase):
    def setUp(self):
        self.strict_rubric = {
            "title": "Photosynthesis Short Answer",
            "answer_type": "short_text",
            "grading_style": "exact",
            "minimum_score": 80,
            "criteria": [
                {
                    "name": "Definition accuracy",
                    "weight": 4,
                    "required_terms": ["sunlight", "energy conversion"],
                },
                {
                    "name": "Key concepts",
                    "weight": 4,
                    "required_terms": ["plants", "chlorophyll"],
                },
                {
                    "name": "Clarity",
                    "weight": 2,
                    "required_terms": ["clear"],
                },
            ],
        }
        self.partial_rubric = {
            "title": "Essay Rubric",
            "answer_type": "essay",
            "grading_style": "partial",
            "minimum_score": 70,
            "description": "- Must mention a thesis\n- Must mention evidence\n- Must mention conclusion",
        }

    @override_settings(GOOGLE_GEMINI_API_KEY="")
    def test_exact_rubric_penalizes_missing_terms(self):
        complete = run_assignment_verification(
            content="Plants use sunlight and chlorophyll for energy conversion into food in a clear explanation.",
            title="Photosynthesis",
            rubric=self.strict_rubric,
        )
        partial = run_assignment_verification(
            content="Plants use sunlight to make food.",
            title="Photosynthesis",
            rubric=self.strict_rubric,
        )

        self.assertEqual(complete["source"], "rubric")
        self.assertGreater(complete["overall_score"], partial["overall_score"])
        self.assertTrue(complete["passed"])
        self.assertFalse(partial["passed"])

    @override_settings(GOOGLE_GEMINI_API_KEY="")
    def test_partial_rubric_accepts_bullet_descriptions(self):
        result = run_assignment_verification(
            content="The essay has a thesis and evidence, but the conclusion is weak.",
            title="Essay",
            rubric=self.partial_rubric,
        )

        self.assertEqual(result["source"], "rubric")
        self.assertEqual(result["rubric"]["grading_style"], "partial")
        self.assertGreaterEqual(len(result["checks"][0]["details"]["criteria"]), 3)
        self.assertIn("thesis", result["checks"][0]["details"]["criteria"][0]["matched_terms"] + result["checks"][0]["details"]["criteria"][0]["missing_terms"])


class PlagiarismEngineTests(SimpleTestCase):
    @override_settings(GOOGLE_GEMINI_API_KEY="")
    def test_plagiarism_check_flags_near_duplicate_text(self):
        text = "The analysis discusses climate policy, public health, and economic pressure in detail."
        result = build_plagiarism_check(
            text,
            corpus_texts=[
                text,
                "A separate article about local agriculture and rainfall patterns.",
            ],
            author_texts=[
                "An earlier draft about a different subject and with a different tone."
            ],
            metadata={"copy_paste_ratio": 0.7, "paste_events": 4},
        )

        self.assertEqual(result["check_type"], "plagiarism_detection")
        self.assertIn("decision", result["details"])
        self.assertGreaterEqual(len(result["details"]["top_matches"]), 1)
        self.assertLess(result["score"], 100)
        self.assertGreater(result["details"]["risk_score"], 0)
        self.assertIn("near_duplicate_to_corpus", result["issues"])

    @override_settings(GOOGLE_GEMINI_API_KEY="")
    def test_run_assignment_verification_includes_plagiarism_analysis(self):
        text = "The analysis discusses climate policy, public health, and economic pressure in detail."
        result = run_assignment_verification(
            content=text,
            title="Policy Analysis",
            plagiarism_context={
                "corpus_texts": [text],
                "author_texts": [
                    "An earlier draft about a different subject and with a different tone."
                ],
                "metadata": {"copy_paste_ratio": 0.7, "paste_events": 4},
            },
        )

        check_types = {check.get("check_type") for check in result.get("checks", []) if isinstance(check, dict)}
        self.assertIn("plagiarism_detection", check_types)
        self.assertIn("plagiarism_analysis", result)
        self.assertGreater(result["plagiarism_analysis"]["risk_score"], 0)
        self.assertGreaterEqual(len(result["plagiarism_analysis"]["top_matches"]), 1)
