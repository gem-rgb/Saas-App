from django.test import SimpleTestCase, override_settings

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
