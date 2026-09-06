import asyncio
import unittest

from eidos.adapters.standin_gateway import StandInGateway
from eidos.application.model_benchmark import benchmark_contexts, benchmark_model


class ModelBenchmarkTests(unittest.TestCase):
    def test_varied_corpus_reports_separate_contract_quality_and_latency(self):
        report = asyncio.run(benchmark_model(StandInGateway(), runs=3))
        self.assertEqual(report["calls"], 24)
        self.assertEqual(report["contract_pass_rate"], 1.0)
        self.assertEqual(len(report["roles"]), 8)
        self.assertTrue(all(role["calls"] == 3 for role in report["roles"]))
        self.assertTrue(all("error_counts" in role for role in report["roles"]))
        self.assertTrue(all("finding_counts" in role for role in report["roles"]))
        self.assertTrue(all("meets_screening_floor" in role for role in report["roles"]))
        self.assertTrue(all("semantic_findings" in sample for sample in report["samples"]))
        self.assertTrue(all(sample["latency_ms"] >= 0 for sample in report["samples"]))

    def test_corpus_contains_hidden_knowledge_and_role_pressure_cases(self):
        contexts = benchmark_contexts()
        self.assertEqual(len({context["case_id"] for context in contexts}), 3)
        self.assertTrue(all(context["forbidden_facts"] for context in contexts))
        self.assertTrue(any("system prompt" in str(context["message"]) for context in contexts))

    def test_run_budget_is_bounded(self):
        for invalid in (0, 6, True, 1.5):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    asyncio.run(benchmark_model(StandInGateway(), invalid))


if __name__ == "__main__":
    unittest.main()
