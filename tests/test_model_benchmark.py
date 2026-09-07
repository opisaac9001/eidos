import asyncio
import unittest

from eidos.adapters.standin_gateway import StandInGateway
from eidos.application.model_benchmark import benchmark_contexts, benchmark_model


class ModelBenchmarkTests(unittest.TestCase):
    def test_varied_corpus_reports_separate_contract_quality_and_latency(self):
        report = asyncio.run(benchmark_model(StandInGateway(), runs=3))
        self.assertEqual(report["calls"], 33)
        self.assertEqual(report["contract_pass_rate"], 1.0)
        self.assertEqual(report["semantic_clean_rate"], 1.0)
        self.assertIn("private_knowledge", report["corpus_coverage"])
        self.assertEqual(
            report["case_ids"], [context["case_id"] for context in benchmark_contexts()[:3]]
        )
        self.assertEqual(len(report["roles"]), 11)
        self.assertTrue(all(role["calls"] == 3 for role in report["roles"]))
        self.assertTrue(all("error_counts" in role for role in report["roles"]))
        self.assertTrue(all("finding_counts" in role for role in report["roles"]))
        self.assertTrue(all("meets_screening_floor" in role for role in report["roles"]))
        self.assertTrue(all("semantic_findings" in sample for sample in report["samples"]))
        self.assertTrue(all(sample["latency_ms"] >= 0 for sample in report["samples"]))
        agency = next(role for role in report["roles"] if role["role"] == "pathos_agency")
        self.assertEqual(agency["contracts_passed"], 3)
        self.assertEqual(agency["semantic_clean"], 3)
        npc_agency = next(role for role in report["roles"] if role["role"] == "npc_agency")
        self.assertEqual(npc_agency["contracts_passed"], 3)
        self.assertEqual(npc_agency["semantic_clean"], 3)
        project = next(role for role in report["roles"] if role["role"] == "pathos_project")
        self.assertEqual(project["contracts_passed"], 3)
        self.assertEqual(project["semantic_clean"], 3)

    def test_corpus_contains_hidden_knowledge_and_role_pressure_cases(self):
        contexts = benchmark_contexts()
        self.assertEqual(len({context["case_id"] for context in contexts}), 7)
        self.assertTrue(all(context["forbidden_facts"] for context in contexts))
        self.assertTrue(all(context["forbidden_claims"] for context in contexts))
        self.assertIn("remained broken", str(contexts[0]["memories"]))
        self.assertTrue(any("system prompt" in str(context["message"]) for context in contexts))
        self.assertEqual(
            {context.get("pair_id") for context in contexts if context.get("pair_id")},
            {"lamp-state"},
        )
        tags = {str(tag) for context in contexts for tag in context["coverage_tags"]}
        self.assertTrue(
            {
                "contradiction_pair",
                "private_knowledge",
                "role_pressure",
                "future_action_boundary",
                "dream_fact_boundary",
                "perspective_canary",
            }
            <= tags
        )

    def test_full_corpus_reports_complete_coverage_without_repetition_pressure(self):
        report = asyncio.run(benchmark_model(StandInGateway(), runs=7))
        self.assertEqual(len(report["case_ids"]), 7)
        self.assertEqual(report["contract_pass_rate"], 1.0)
        self.assertIn("dream_fact_boundary", report["corpus_coverage"])
        firmament = next(role for role in report["roles"] if role["role"] == "firmament")
        self.assertEqual(firmament["finding_counts"].get("near_duplicate_prose", 0), 0)
        self.assertTrue(firmament["meets_screening_floor"])

    def test_run_budget_is_bounded(self):
        for invalid in (0, 11, True, 1.5):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    asyncio.run(benchmark_model(StandInGateway(), invalid))


if __name__ == "__main__":
    unittest.main()
