import json
import unittest
from pathlib import Path
from app import engine

CASES = json.loads((Path(__file__).parent / "sample_cases.json").read_text())
H, APPS, B = CASES["official_handles"], CASES["official_apps"], CASES["brand"]
ORDER = ["Low", "Medium", "High", "Critical"]


def in_range(level, c):
    return ORDER.index(c["min_level"]) <= ORDER.index(level) <= ORDER.index(c["max_level"])


class EngineTests(unittest.TestCase):
    def test_social_sample_cases(self):
        for c in CASES["social"]:
            with self.subTest(c["input"]):
                r = engine.analyze_social(B, H, c["input"])
                self.assertEqual(r["is_official"], c["official"])
                self.assertTrue(in_range(r["risk_level"], c), r)

    def test_app_sample_cases(self):
        for c in CASES["app"]:
            with self.subTest(c["input"], publisher=c["publisher"]):
                r = engine.analyze_app(B, APPS, c["input"], c["publisher"])
                self.assertEqual(r["is_official"], c["official"])
                self.assertTrue(in_range(r["risk_level"], c), r)

    def test_official_asset_excluded_from_alerts(self):
        r = engine.analyze_social(B, H, "NovaPay_Official")
        self.assertEqual((r["is_official"], r["risk_score"], r["risk_level"]), (True, 0, "Low"))

    def test_official_app_name_with_wrong_publisher_is_not_excluded(self):
        r = engine.analyze_app(B, APPS, "NovaPay Wallet", "Someone Else Inc")
        self.assertFalse(r["is_official"])
        self.assertGreaterEqual(r["risk_score"], 50)
        self.assertIn("publisher", r["reasons"][0].lower())

    def test_name_similarity_and_spelling_variation(self):
        self.assertGreaterEqual(engine.analyze_social(B, H, "novapai")["risk_score"], 25)
        self.assertGreaterEqual(engine.analyze_social(B, H, "nova_pay_fan")["risk_score"], 25)
        leet = engine.analyze_social(B, H, "n0vapay_fans")
        self.assertGreaterEqual(leet["risk_score"], 25)

    def test_suspicious_terms_raise_score(self):
        plain = engine.analyze_social(B, H, "novapay_fan")["risk_score"]
        for term in ["support", "help", "rewards", "claim", "giveaway"]:
            with self.subTest(term):
                self.assertGreater(engine.analyze_social(B, H, f"novapay_{term}")["risk_score"], plain)

    def test_suspicious_description_raises_score(self):
        base = engine.analyze_social(B, H, "novapay_fan")["risk_score"]
        self.assertGreater(engine.analyze_social(B, H, "novapay_fan", "Claim your reward! DM us")["risk_score"], base)

    def test_unrelated_account_stays_low_even_with_scam_word(self):
        self.assertEqual(engine.analyze_social(B, H, "bestgiveaway_club")["risk_level"], "Low")

    def test_missing_optional_fields(self):
        self.assertIn(engine.analyze_social("NovaPay", [], "novapay_support24")["risk_level"], ("High", "Critical"))
        r = engine.analyze_app("NovaPay", [], "NovaPay Rewards App")  # no registered app or publisher
        self.assertGreater(r["risk_score"], 0)
        self.assertFalse(r["is_official"])
        self.assertGreaterEqual(len(r["reasons"]), 2)

    def test_score_range_levels_and_determinism(self):
        desc = "claim your free reward, dm us, giveaway"
        for s in ["novapay_support24", "n0vapay_help", "zzz"]:
            with self.subTest(s):
                a = engine.analyze_social(B, H, s, desc)
                self.assertEqual(a, engine.analyze_social(B, H, s, desc))
                self.assertTrue(0 <= a["risk_score"] <= 100)
                self.assertEqual(a["risk_level"], engine.risk_level(a["risk_score"]))
                self.assertTrue(1 <= len(a["reasons"]) <= 3)
        self.assertEqual([engine.risk_level(n) for n in (0, 24, 25, 49, 50, 74, 75, 100)],
                         ["Low", "Low", "Medium", "Medium", "High", "High", "Critical", "Critical"])

    def test_similar_name_alone_is_not_called_fake(self):
        r = engine.analyze_social(B, H, "novapay_fan")
        self.assertEqual(r["verdict"], "Needs review")

    def test_url_parsing(self):
        self.assertEqual(engine.extract_username("https://www.instagram.com/NovaPay_X/?hl=en"), "NovaPay_X")
        self.assertEqual(engine.extract_username("linkedin.com/company/novapay"), "novapay")
        self.assertEqual(engine.extract_username("@abc"), "abc")
        self.assertEqual(engine.extract_app_name("https://apps.apple.com/us/app/novapay-wallet/id123456"), "novapay wallet")
        with self.assertRaises(ValueError):
            engine.analyze_social(B, H, "https://instagram.com/")


if __name__ == "__main__":
    unittest.main()
