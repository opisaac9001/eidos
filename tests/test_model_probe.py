import asyncio
import unittest

from eidos.adapters.standin_gateway import StandInGateway
from eidos.application.model_probe import probe_roles


class ModelProbeTests(unittest.TestCase):
    def test_stand_in_is_contract_clean_and_semantically_warning_free(self):
        result = asyncio.run(probe_roles(StandInGateway()))
        self.assertTrue(result["passed"])
        self.assertTrue(result["semantic_passed"])
        self.assertTrue(all("semantic_findings" in role for role in result["roles"]))


if __name__ == "__main__":
    unittest.main()
