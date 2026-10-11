import unittest
from app import services
from app.repository import MemoryRepository, SupabaseRepository, DatabaseError


class FakeQuery:
    """Tiny stand-in for the supabase-py query builder (only the methods we use)."""
    def __init__(self, db, table):
        self.db, self.table, self.op, self.payload, self.filters, self.cols, self.desc, self.lim = db, table, "select", None, [], "*", False, None
    def select(self, cols="*"): self.cols = cols; return self
    def insert(self, p): self.op, self.payload = "insert", p; return self
    def update(self, p): self.op, self.payload = "update", p; return self
    def delete(self): self.op = "delete"; return self
    def eq(self, k, v): self.filters.append((k, v)); return self
    def order(self, col, desc=False): self.desc = desc; return self
    def limit(self, n): self.lim = n; return self
    def execute(self):
        if self.db.fail: raise RuntimeError("connection refused")
        rows = self.db.tables[self.table]
        match = [r for r in rows if all(r.get(k) == v for k, v in self.filters)]
        out = []
        if self.op == "insert":
            for p in (self.payload if isinstance(self.payload, list) else [self.payload]):
                self.db.n += 1
                row = {"id": f"id{self.db.n}", "created_at": f"2026-01-01T00:00:{self.db.n:02d}+00:00", **p}
                rows.append(row); out.append(row)
        elif self.op == "update":
            for r in match: r.update(self.payload)
        elif self.op == "delete":
            self.db.tables[self.table] = [r for r in rows if r not in match]
        else:
            out = [dict(r) for r in match]
            if self.desc: out.reverse()
            if self.lim: out = out[:self.lim]
            if "brands(" in self.cols:
                for r in out:
                    r["brands"] = next(({"name": b["name"]} for b in self.db.tables["brands"] if b["id"] == r["brand_id"]), None)
        return type("Res", (), {"data": out})()


class FakeSupabase:
    def __init__(self): self.tables = {"brands": [], "official_assets": [], "scan_results": []}; self.n = 0; self.fail = False
    def table(self, name): return FakeQuery(self, name)



def repos():
    """Run every test against the in-memory repo and the Supabase repo (fake client)."""
    return [("memory", MemoryRepository()), ("supabase-fake", SupabaseRepository(FakeSupabase()))]


class ServiceTests(unittest.TestCase):
    def each(self):
        for name, repo in repos():
            with self.subTest(repo=name):
                yield repo

    def test_brand_save_and_edit(self):
        for repo in self.each():
            p = services.save_profile(repo, "Acme", "https://acme.example", ["@acme_hq"], [{"name": "Acme App", "publisher": "Acme Ltd"}])
            self.assertEqual(p["socials"], ["acme_hq"])
            self.assertEqual(p["apps"][0]["publisher"], "Acme Ltd")
            p2 = services.save_profile(repo, "Acme Corp", "", ["acme_corp"], [])
            self.assertEqual((p2["id"], p2["name"], p2["socials"], p2["apps"]), (p["id"], "Acme Corp", ["acme_corp"], []))
            self.assertEqual(len(repo.list_profiles()), 1)

    def test_scan_is_saved_and_listed_with_reasons(self):
        for repo in self.each():
            services.load_demo_brand(repo)
            r = services.scan_social(repo, "NovaPay", "novapay_support24", "Instagram", "")
            self.assertTrue(r["fictional_demo"])
            self.assertEqual(r["stored_in"], repo.mode)
            d = services.dashboard(repo)
            self.assertEqual(d["stats"], {"total_scans": 1, "high_risk": 1, "social_scans": 1, "app_scans": 0})
            saved = d["recent"][0]
            self.assertEqual((saved["submitted_identifier"], saved["reasons"], saved["brand_name"]),
                             ("novapay_support24", r["reasons"], "NovaPay"))

    def test_official_scans_not_counted_as_high_risk(self):
        for repo in self.each():
            services.load_demo_brand(repo)
            services.scan_social(repo, "NovaPay", "novapay_official", "Instagram")
            services.scan_app(repo, "NovaPay", "NovaPay Wallet", "NovaPay Technologies Ltd")
            s = services.dashboard(repo)["stats"]
            self.assertEqual((s["total_scans"], s["high_risk"], s["app_scans"]), (2, 0, 1))

    def test_scan_works_with_only_brand_name(self):
        for repo in self.each():
            self.assertIn(services.scan_social(repo, "Zephyr", "zephyr_giveaway", "X")["risk_level"], ("High", "Critical"))
            self.assertGreater(services.scan_app(repo, "Zephyr", "Zephyr Bonus App")["risk_score"], 0)

    def test_input_validation(self):
        bad = [("", "x", "X"), ("A", "", "X"), ("A", "x", "MySpace"), ("A", "x" * 300, "X"), ("A", "bad\x00name", "X")]
        for name, repo in repos():
            for args in bad:
                with self.subTest(repo=name, args=args[:2]):
                    with self.assertRaises(ValueError):
                        services.scan_social(repo, *args)

    def test_database_failure_is_reported_not_crashed(self):
        fake = FakeSupabase(); r = SupabaseRepository(fake); fake.fail = True
        with self.assertRaises(DatabaseError):
            services.scan_social(r, "NovaPay", "novapay_x", "X")

    def test_demo_brand_refuses_to_overwrite_real_brand(self):
        for repo in self.each():
            services.save_profile(repo, "RealCo")
            with self.assertRaises(ValueError):
                services.load_demo_brand(repo)

    def test_repository_falls_back_to_demo_without_credentials(self):
        import os
        from unittest import mock
        from app.repository import create_repository
        with mock.patch.dict(os.environ, {}, clear=True):
            r, msg = create_repository()
        self.assertEqual(r.mode, "demo")
        self.assertIn("Demo mode", msg)


if __name__ == "__main__":
    unittest.main()
