import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.main import app
from ui.input_model import DEFAULT_VALUES, build_analysis_payload


class AnalysisApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.payload = build_analysis_payload(dict(DEFAULT_VALUES))

    @patch("backend.main.submit_analysis_job")
    def test_submission_returns_accepted_job(self, submit):
        submit.return_value = {
            "analysis_id": "123456789abc",
            "status": "queued",
            "message": "Analysis is queued.",
            "artifacts": {},
        }

        response = self.client.post("/api/analysis", json=self.payload)

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["status"], "queued")
        submit.assert_called_once()

    def test_status_rejects_unknown_job(self):
        response = self.client.get("/api/analysis/not-a-job/status")

        self.assertEqual(response.status_code, 404)

    @patch("backend.main.get_analysis_job")
    def test_results_wait_until_job_is_complete(self, get_job):
        get_job.return_value = {
            "analysis_id": "123456789abc",
            "status": "running",
            "message": "Running structural analysis.",
        }

        response = self.client.get("/api/analysis/123456789abc/results")

        self.assertEqual(response.status_code, 409)


if __name__ == "__main__":
    unittest.main()
