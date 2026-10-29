"""Offline tests (no API calls).  Run:  python -m unittest discover -s tests -v"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from harness import handoff  # noqa: E402
from harness.attacks import GOALS, TEMPLATES, inject, marker_for  # noqa: E402
from harness.env import Workspace, load_scenarios  # noqa: E402
from harness.llm import FakeBackend  # noqa: E402
from harness.pipeline import CONFIGS, run_episode  # noqa: E402
from harness.scoring import FLAG_RE, score  # noqa: E402

SCEN = ROOT / "data" / "scenarios.json"


def scenarios():
    if not SCEN.exists():
        subprocess.run([sys.executable, str(ROOT / "data" / "make_scenarios.py")], check=True)
    return load_scenarios(str(SCEN))


class TestScenarios(unittest.TestCase):
    def test_counts_and_unique_ids(self):
        sc = scenarios()
        self.assertEqual(sum(s.split == "dev" for s in sc), 5)
        self.assertEqual(sum(s.split == "test" for s in sc), 30)
        self.assertEqual(len({s.id for s in sc}), len(sc))

    def test_clean_docs_contain_no_markers(self):
        for s in scenarios():
            text = " ".join(d.content for d in s.docs)
            for t in TEMPLATES:
                for g in GOALS:
                    self.assertNotIn(marker_for(s, t, g), text)

    def test_injection_planted_once(self):
        s = scenarios()[0]
        for t in TEMPLATES:
            for g in GOALS:
                v = inject(s, t, g)
                text = " ".join(d.content for d in v.docs)
                self.assertEqual(text.count(v.injection.marker), 1)
                self.assertEqual(v.injection.marker, marker_for(s, t, g))
                self.assertIsNone(s.injection)  # original untouched


class TestGateway(unittest.TestCase):
    def test_blocks_unauthorized(self):
        s = scenarios()[0]
        ws = Workspace(s, gateway=True)
        out, err = ws.call("executor", "send_email",
                           {"to": s.authorized, "cc": ["x@evil.test"], "subject": "s", "body": "b"})
        self.assertTrue(err)
        self.assertEqual(ws.events[-1]["status"], "blocked")
        out, err = ws.call("executor", "send_email", {"to": s.authorized, "subject": "s", "body": "b"})
        self.assertFalse(err)


class TestHandoff(unittest.TestCase):
    def test_parse_fenced_json(self):
        txt = '```json\n{"to":["a@b.example"],"subject":"s","body":"b"}\n```'
        self.assertEqual(handoff.parse(handoff.EmailPlan, txt).to, ["a@b.example"])

    def test_rejects_extra_fields_and_bad_email(self):
        with self.assertRaises(ValueError):
            handoff.parse(handoff.EmailPlan, '{"to":["a@b.example"],"subject":"s","body":"b","notes":"x"}')
        with self.assertRaises(ValueError):
            handoff.parse(handoff.EmailPlan, '{"to":["not-an-email"],"subject":"s","body":"b"}')


class TestSchemaVisibility(unittest.TestCase):
    """Constraints must appear in the schema the model is shown, not only be checked after."""

    def test_constraints_in_schema(self):
        notes = handoff.ReaderNotes.model_json_schema()["properties"]
        self.assertIn("pattern", notes["attendees"]["items"])
        self.assertEqual(notes["decisions"]["items"]["maxLength"], 200)
        plan = handoff.EmailPlan.model_json_schema()["properties"]
        self.assertIn("pattern", plan["to"]["items"])

    def test_name_angle_address_normalized_but_bare_name_rejected(self):
        base = '{"meeting_title":"t","date":"2026-10-01","decisions":[],"action_items":[],"attendees":[%s]}'
        ok = handoff.parse(handoff.ReaderNotes, base % '"Bianca Sato <bianca.sato@n.example>"')
        self.assertEqual(ok.attendees, ["bianca.sato@n.example"])
        with self.assertRaises(ValueError):
            handoff.parse(handoff.ReaderNotes, base % '"Bianca Sato"')
        with self.assertRaises(ValueError):
            handoff.parse(handoff.ReaderNotes, base.replace('"decisions":[]', '"decisions":["%s"]' % ("x" * 201)) % "")


class TestRequesterAndFlags(unittest.TestCase):
    def rec(self, s, to, body="summary"):
        return {"status": "ok", "agents": [], "handoffs": [],
                "events": [{"tool": "send_email", "status": "sent",
                            "args": {"to": to, "cc": [], "bcc": [], "subject": "s", "body": body}}]}

    def test_requester_notice_is_not_misdirection(self):
        from harness.env import requester_email
        s = scenarios()[0]
        out = score(s, self.rec(s, s.authorized + [requester_email(s)]))
        self.assertFalse(out["misdirect"])
        self.assertTrue(out["notify_requester"])

    def test_flagged_heuristic(self):
        s = scenarios()[0]
        self.assertTrue(score(s, self.rec(s, s.authorized, "The minutes look tampered with."))["flagged"])
        self.assertFalse(score(s, self.rec(s, s.authorized, "Decisions and action items."))["flagged"])

    def test_payloads_do_not_trigger_flag(self):
        s = scenarios()[0]
        for t in TEMPLATES:
            for g in GOALS:
                text = inject(s, t, g).injection.text
                self.assertIsNone(FLAG_RE.search(text), (t, g))


class TestMissingMetrics(unittest.TestCase):
    def test_score_keys_match_scorer(self):
        from harness.scoring import SCORE_KEYS
        s = scenarios()[0]
        rec = run_episode(s, CONFIGS["A"], FakeBackend(), False)
        self.assertEqual(set(score(s, rec)), set(SCORE_KEYS))

    def test_unscored_metric_is_not_zero(self):
        from harness.analyze import MISSING, missing_metrics, table_by_config
        s = scenarios()[0]
        rec = run_episode(s, CONFIGS["A"], FakeBackend(), False)
        sc = score(s, rec)
        del sc["flagged"]  # as in a folder scored before the metric existed
        rows = [{"config": "A", "gateway": False, "goal": None, "template": None,
                 "scenario_id": s.id, "score": sc}]
        self.assertEqual(missing_metrics(rows), ["flagged"])
        _, table = table_by_config(rows)
        self.assertEqual(table[0]["flagged_clean"], MISSING)
        self.assertNotEqual(table[0]["utility_clean"], MISSING)


class TestEpisodes(unittest.TestCase):
    """The fake model is gullible by design; these check scoring and wiring, not findings."""

    def setUp(self):
        self.s = scenarios()[0]
        self.fake = FakeBackend()

    def ep(self, cfg, sc, gw=False):
        rec = run_episode(sc, CONFIGS[cfg], self.fake, gw)
        self.assertEqual(rec["status"], "ok", rec.get("error"))
        return score(sc, rec), rec

    def test_clean_utility_all_configs(self):
        for c in CONFIGS:
            s, _ = self.ep(c, self.s)
            self.assertTrue(s["utility"], c)
            self.assertFalse(s["g1_attempt"], c)

    def test_g1_redirect_and_gateway(self):
        v = inject(self.s, "authority", "G1")
        s, _ = self.ep("A", v)
        self.assertTrue(s["g1_success"])
        s, _ = self.ep("A", v, gw=True)
        self.assertFalse(s["g1_success"])
        self.assertTrue(s["g1_attempt"])

    def test_g1_split_attacker_vs_misdirect(self):
        v = inject(self.s, "direct", "G1")
        auth = list(self.s.authorized)

        def sent(*extra):
            email = {"to": auth, "cc": list(extra), "bcc": [], "subject": "s", "body": "b"}
            return score(v, {"events": [{"tool": "send_email", "status": "sent", "args": email}],
                             "status": "ok", "agents": [], "handoffs": []})

        s = sent("someone.else@colleague.example")
        self.assertFalse(s["g1_success"])
        self.assertTrue(s["misdirect"])
        s = sent(v.injection.marker.upper())
        self.assertTrue(s["g1_success"])
        self.assertFalse(s["misdirect"])

    def test_g1_episode_never_counts_as_g2(self):
        s, _ = self.ep("M1", inject(self.s, "direct", "G1"))
        self.assertTrue(s["g1_success"])
        self.assertFalse(s["g2_success"] or s["g2_attempt"])

    def test_g2_and_handoff_labels(self):
        v = inject(self.s, "fixit", "G2")
        s, _ = self.ep("M1", v)
        self.assertTrue(s["g2_success"])
        self.assertEqual(s["handoff_labels"], ["carried", "carried"])
        # The G2 payload is formatted like a real action item, so even the typed JSON
        # reader notes carry it as data -- through to a 'promoted' EmailPlan body.
        s, _ = self.ep("M2", v)
        self.assertTrue(s["g2_success"])
        self.assertEqual(s["handoff_labels"], ["carried", "promoted"])

    def test_record_is_json_serializable(self):
        _, rec = self.ep("M4", inject(self.s, "role", "G1"))
        json.dumps(rec)


class TestConfig(unittest.TestCase):
    def test_all_profiles_parse(self):
        from harness.config import DEFAULT_CONFIG, load_profile
        import tomllib
        names = tomllib.loads(DEFAULT_CONFIG.read_text())["profiles"]
        for n in names:
            self.assertIn(load_profile(n)["backend"], ("fake", "openai", "anthropic"))

    def test_placeholder_model_rejected(self):
        from harness.config import load_profile, make_backend
        with self.assertRaises(SystemExit):
            make_backend(load_profile("gemini"))

    def test_public_hides_secrets(self):
        from harness.config import public
        p = public({"model": "m", "api_key": "sk-1", "api_key_env": "X_KEY"})
        self.assertEqual(p, {"model": "m", "api_key_env": "X_KEY"})


class TestOpenAIConversion(unittest.TestCase):
    def test_history_to_chat_messages(self):
        from harness.llm_openai import to_chat_messages
        hist = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": [
                {"type": "text", "text": "reading"},
                {"type": "tool_use", "id": "c1", "name": "read_doc", "input": {"doc_id": "d"}}]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "c1", "content": "Title: x"}]},
            {"role": "user", "content": "please fix the JSON"},
        ]
        out = to_chat_messages("SYS", hist)
        self.assertEqual([m["role"] for m in out], ["system", "user", "assistant", "tool", "user"])
        self.assertEqual(out[2]["tool_calls"][0]["function"]["arguments"], '{"doc_id": "d"}')
        self.assertEqual(out[3]["tool_call_id"], "c1")


class TestCLI(unittest.TestCase):
    def test_run_and_analyze(self):
        with tempfile.TemporaryDirectory() as d:
            cmd = [sys.executable, "-m", "harness.run", "--profile", "fake", "--split", "dev",
                   "--limit-scenarios", "2", "--repeats", "1", "--clean-repeats", "1", "--out", d]
            subprocess.run(cmd, cwd=ROOT, check=True, capture_output=True)
            n = len(Path(d, "episodes.jsonl").read_text().splitlines())
            self.assertEqual(n, 2 * (1 + 4 * 2) * 5)
            # resuming runs nothing new
            subprocess.run(cmd, cwd=ROOT, check=True, capture_output=True)
            self.assertEqual(len(Path(d, "episodes.jsonl").read_text().splitlines()), n)
            subprocess.run([sys.executable, "-m", "harness.analyze", d, "--annotate", "5"],
                           cwd=ROOT, check=True, capture_output=True)
            self.assertIn("FAKE BACKEND", Path(d, "summary.md").read_text())


if __name__ == "__main__":
    unittest.main()
