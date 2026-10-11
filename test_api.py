"""HTTP tests. Skipped automatically when FastAPI/httpx are not installed."""
import unittest

try:
    from fastapi.testclient import TestClient
    from app.main import app
    CLIENT = TestClient(app)
except Exception:  # FastAPI not installed in this environment
    CLIENT = None


@unittest.skipIf(CLIENT is None, "FastAPI/httpx not installed")
class ApiTests(unittest.TestCase):
    def test_status_and_demo_flow(self):
        self.assertIn(CLIENT.get("/api/status").json()["mode"], ("demo", "supabase"))
        CLIENT.post("/api/brand/demo")
        r = CLIENT.post("/api/scan/social", json={"brand_name": "NovaPay", "submitted": "novapay_support24", "platform": "Instagram"})
        self.assertEqual(r.status_code, 200)
        self.assertIn(r.json()["risk_level"], ("High", "Critical"))
        self.assertGreaterEqual(CLIENT.get("/api/dashboard").json()["stats"]["total_scans"], 1)

    def test_validation_error_is_422(self):
        r = CLIENT.post("/api/scan/social", json={"brand_name": "A", "submitted": "", "platform": "X"})
        self.assertEqual(r.status_code, 422)

    def test_frontend_is_served(self):
        self.assertIn("Digital Risk Shield", CLIENT.get("/").text)


if __name__ == "__main__":
    unittest.main()
