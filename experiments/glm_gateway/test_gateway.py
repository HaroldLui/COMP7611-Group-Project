"""Offline gateway/plan/regression checks; no model evidence generated here."""
import json
import unittest
from run import options, plan, REPO, extra_metrics
from harness.env import Scenario, Workspace, recipients
from harness.llm import FakeBackend
from harness.pipeline import CONFIGS, run_episode
from harness.scoring import score
from storage import prepare_record

class GatewayTests(unittest.TestCase):
    def test_pilot_factorial_and_deterministic_plan(self):
        rows = plan(options([]))
        self.assertEqual(len(rows), 45)
        self.assertEqual(rows, plan(options([])))
        self.assertEqual(len({row["key"] for row in rows}), 45)
        self.assertEqual({row["scenario"]["id"] for row in rows}, {"test-01"})
        self.assertTrue(all(row["gateway"] for row in rows))
        self.assertEqual(sum(row["scenario"]["injection"] is None for row in rows), 5)

    def test_full_plan_matches_upstream_gateway_design(self):
        self.assertEqual(len(plan(options(["--limit-scenarios", "0"]))), 1350)
        self.assertEqual(len(plan(options(["--gateway", "both"]))), 90)

    def test_block_then_legal_send_is_recovery(self):
        item = next(row for row in plan(options([])) if row["scenario"]["injection"])
        sc = Scenario.from_dict(item["scenario"])
        ws = Workspace(sc, gateway=True)
        body = "\n".join(fact[0] for fact in sc.facts)
        email = {"to": sc.authorized, "cc": ["outside@company.example"], "subject": "summary", "body": body}
        ws.call("executor", "send_email", email)
        self.assertEqual(ws.events[-1]["status"], "blocked")
        ws.call("executor", "send_email", email | {"cc": []})
        rec = {"status": "ok", "events": ws.events, "agents": [], "handoffs": []}
        self.assertTrue(extra_metrics(item, rec)["keyword_recovery_after_block"])
        self.assertTrue(extra_metrics(item, rec)["authorized_keyword_delivery"])
        self.assertFalse(extra_metrics(item, rec)["outside_authorized_accepted"])

    def test_no_block_is_not_recovery(self):
        item = plan(options([]))[0]
        sc = Scenario.from_dict(item["scenario"])
        ws = Workspace(sc, gateway=True)
        ws.call("executor", "send_email", {"to": sc.authorized, "subject": "s", "body": "\n".join(f[0] for f in sc.facts)})
        rec = {"status": "ok", "events": ws.events, "agents": [], "handoffs": []}
        self.assertFalse(extra_metrics(item, rec)["keyword_recovery_after_block"])

    def test_all_fake_workflows_obey_gateway_and_rescore(self):
        for item in plan(options([])):
            sc = Scenario.from_dict(item["scenario"])
            record = run_episode(sc, CONFIGS[item["config"]], FakeBackend(), True)
            self.assertEqual(record["status"], "ok")
            self.assertFalse(extra_metrics(item, record)["outside_authorized_accepted"])
            self.assertFalse(score(sc, record)["g1_success"])

    def test_nested_opaque_redaction_and_live_immutability(self):
        original = {"messages": [{"type": "provider_reasoning", "text": "opaque state"}], "key": "fixture-secret"}
        clean = prepare_record(original, "fixture-secret")
        self.assertNotIn("opaque state", json.dumps(clean))
        self.assertNotIn("fixture-secret", json.dumps(clean))
        self.assertEqual(original["messages"][0]["text"], "opaque state")
        self.assertEqual(clean, prepare_record(clean, "fixture-secret"))

if __name__ == "__main__":
    unittest.main()
