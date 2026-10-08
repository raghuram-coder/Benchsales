"""Core logic tests (stdlib unittest; no network, no web framework needed).

Run from the project root:   python -m unittest discover -s tests -v
"""
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import db, emptype, matcher, portals, usa  # noqa: E402
from app.sources import urlimport  # noqa: E402


class EmpTypeTests(unittest.TestCase):
    def check(self, et, title, desc, expected):
        self.assertEqual(set(emptype.classify(et, title, desc)), set(expected),
                         f"{et!r} {title!r} {desc!r}")

    def test_aggregator_type_words(self):
        self.check("full_time", "Java Developer", "", ["fulltime"])
        self.check("CONTRACTOR", "QA Engineer", "", ["contract"])
        self.check("part_time", "Dev", "", ["parttime"])

    def test_c2c_w2_in_description(self):
        self.check("", "Java Dev", "Open to C2C or W2. Hybrid in Dallas, TX",
                   ["c2c", "w2", "contract"])
        self.check("", "Dev", "Corp-to-Corp, 1099 and W2 fine, 12 month contract",
                   ["c2c", "w2", "1099", "contract"])
        self.check("", "Sr Python Dev (C2C)", "", ["c2c", "contract"])

    def test_negations(self):
        self.check("", "Dev", "W2 only. No C2C. No third party.", ["w2"])
        self.check("", "Dev", "C2C not accepted. W2 candidates only", ["w2"])
        self.check("", "Dev", "C2C is not allowed", [])
        self.check("", "Dev", "No corp to corp please; W2 contract role",
                   ["w2", "contract"])

    def test_contract_to_hire(self):
        self.check("", "Data Eng", "Contract to hire, W2", ["w2", "contract", "c2h"])

    def test_boilerplate_is_not_a_type(self):
        self.check("", "Data Eng", "Great benefits for full-time employees", [])
        self.check("", "Contracts Manager", "manage vendor agreements", [])

    def test_filter_semantics(self):
        self.assertTrue(emptype.matches_filter(["c2c"], ["c2c", "w2"]))
        self.assertFalse(emptype.matches_filter(["fulltime"], ["c2c", "w2"]))
        self.assertFalse(emptype.matches_filter([], ["c2c"]))
        self.assertTrue(emptype.matches_filter([], ["c2c"], include_unspecified=True))
        self.assertTrue(emptype.matches_filter(["parttime"], []))


class UsaTests(unittest.TestCase):
    def test_locations(self):
        yes = ["Houston, TX", "Remote", "Worldwide", "", "Austin, Texas",
               "Remote - USA", "Americas", "Dallas-Fort Worth, TX",
               "Remote (Canada or US)"]
        no = ["Berlin, Germany", "Europe", "London, UK", "Toronto, Ontario, Canada",
              "Remote, India", "Bengaluru, Karnataka, India"]
        for loc in yes:
            self.assertTrue(usa.is_us_job({"location": loc}), loc)
        for loc in no:
            self.assertFalse(usa.is_us_job({"location": loc}), loc)


class PortalTests(unittest.TestCase):
    def test_links(self):
        links = {l["id"]: l["url"] for l in
                 portals.build_links("Java Developer", "Houston, TX",
                                     ["fulltime", "c2c", "w2"], 7)}
        for pid in ("dice", "indeed", "linkedin", "ziprecruiter", "glassdoor"):
            self.assertIn(pid, links)
            self.assertTrue(links[pid].startswith("https://"))
        self.assertIn("Java+Developer", links["dice"])
        self.assertIn("filters.employmentType=THIRD_PARTY", links["dice"])
        self.assertIn("f_JT=F%2CC", links["linkedin"])
        self.assertIn("C2C", links["indeed"])


class DbTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._old = db.DB_PATH
        db.DB_PATH = Path(self.tmp.name) / "t.db"
        db.init_db()

    def tearDown(self):
        db.DB_PATH = self._old
        self.tmp.cleanup()

    def job(self, n, **kw):
        j = {"source": "t", "source_id": f"id{n}", "title": f"Java Dev {n}",
             "company": f"Co{n}", "location": "Houston, TX", "remote_flag": 0,
             "url": "", "description": "Java Spring Boot", "posted_at": "",
             "salary": "", "employment_type": ""}
        j.update(kw)
        return j

    def test_tags_stored_and_filtered(self):
        db.insert_job(self.job(1, employment_type="full_time"))
        db.insert_job(self.job(2, description="C2C or W2 contract"))
        db.insert_job(self.job(3, description="W2 only. No C2C."))
        db.insert_job(self.job(4))  # nothing detectable
        titles = lambda **kw: sorted(j["title"] for j in db.list_jobs(**kw))
        self.assertEqual(titles(emp=["c2c"]), ["Java Dev 2"])
        self.assertEqual(titles(emp=["w2"]), ["Java Dev 2", "Java Dev 3"])
        self.assertEqual(titles(emp=["fulltime", "c2c"]), ["Java Dev 1", "Java Dev 2"])
        self.assertEqual(titles(emp=["c2c"], include_unspecified=True),
                         ["Java Dev 2", "Java Dev 4"])
        self.assertEqual(len(db.list_jobs()), 4)
        self.assertIn("c2c", db.list_jobs(emp=["c2c"])[0]["emp_tags"])

    def test_dedupe_uses_location(self):
        self.assertTrue(db.insert_job(self.job(1, title="Java Dev", company="Acme")))
        # same title+company+location from another source -> duplicate
        self.assertIsNone(db.insert_job(self.job(2, title="java dev", company="ACME")))
        # same title+company, different city -> a separate opening
        self.assertTrue(db.insert_job(self.job(3, title="Java Dev", company="Acme",
                                               location="Dallas, TX")))

    def test_migration_from_old_schema(self):
        p = Path(self.tmp.name) / "old.db"
        con = sqlite3.connect(p)
        con.executescript("""
        CREATE TABLE consultants (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
          email TEXT DEFAULT '', phone TEXT DEFAULT '', location TEXT DEFAULT '',
          visa_status TEXT DEFAULT '', linkedin_url TEXT DEFAULT '', notes TEXT DEFAULT '',
          created_at TEXT NOT NULL);
        CREATE TABLE jobs (id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT NOT NULL,
          source_id TEXT NOT NULL, title TEXT DEFAULT '', company TEXT DEFAULT '',
          location TEXT DEFAULT '', remote_flag INTEGER DEFAULT 0, url TEXT DEFAULT '',
          description TEXT DEFAULT '', posted_at TEXT DEFAULT '', salary TEXT DEFAULT '',
          employment_type TEXT DEFAULT '', fetched_at TEXT NOT NULL, UNIQUE(source, source_id));
        INSERT INTO jobs(source, source_id, title, description, fetched_at)
          VALUES ('x','1','Old job','Corp to corp welcome','2026-01-01');
        """)
        con.commit()
        con.close()
        db.DB_PATH = p
        db.init_db()
        db.init_db()  # idempotent
        j = db.list_jobs(emp=["c2c"])
        self.assertEqual([x["title"] for x in j], ["Old job"])
        c = db.create_consultant({"name": "A", "emp_pref": "w2, c2c ,bogus"})
        self.assertEqual(c["emp_pref"], "w2,c2c")

    def test_matcher_respects_consultant_preference(self):
        w2_only = {"emp_pref": "w2"}
        self.assertTrue(matcher.emp_compatible(w2_only, ["w2", "c2c"]))
        self.assertFalse(matcher.emp_compatible(w2_only, ["c2c"]))
        self.assertTrue(matcher.emp_compatible(w2_only, []))      # unknown passes
        self.assertTrue(matcher.emp_compatible({"emp_pref": ""}, ["c2c"]))  # no pref

    def test_run_all_end_to_end(self):
        c1 = db.create_consultant({"name": "W2 Person", "emp_pref": "w2"})
        c2 = db.create_consultant({"name": "Any Person"})
        txt = "Senior Java Developer\nJava Spring Boot microservices REST API AWS Docker PostgreSQL"
        for c in (c1, c2):
            db.upsert_resume(c["id"], "r.txt", txt, matcher.extract_skills(txt))
        desc = ("Requirements:\n- Java, Spring Boot, microservices, REST API\n"
                "- AWS, Docker, PostgreSQL\n")
        db.insert_job(self.job(1, title="Senior Java Developer",
                               description=desc + "C2C only"))
        db.insert_job(self.job(2, title="Senior Java Developer", company="Other",
                               description=desc + "W2 only"))
        n = matcher.run_all(threshold=10)
        by_c = {}
        for m in db.list_matches():
            by_c.setdefault(m["consultant_name"], []).append(m["emp_tags"])
        self.assertEqual(len(by_c["Any Person"]), 2)
        self.assertEqual(by_c["W2 Person"], [["w2"]])  # C2C-only job skipped
        self.assertEqual(n, 3)
        self.assertEqual(matcher.run_all(threshold=10), 0)  # idempotent


class SsrfTests(unittest.TestCase):
    def test_private_hosts_blocked(self):
        for u in ["http://127.0.0.1:8741/api/settings",
                  "http://169.254.169.254/latest/meta-data/",
                  "http://localhost/", "file:///etc/passwd",
                  "http://10.0.0.5/", "http://[::1]/"]:
            with self.assertRaises(ValueError, msg=u):
                urlimport._assert_public(u)


if __name__ == "__main__":
    unittest.main()
