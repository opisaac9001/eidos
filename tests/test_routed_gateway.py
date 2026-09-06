import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from eidos.adapters.routed_gateway import CAPABILITIES, RoutedModelGateway, routed_gateway_from_file
from eidos.ports.model_gateway import ModelMessage, ModelRequest, ModelResponse


class Gateway:
    def __init__(self, name):
        self.name = name
        self.calls = []

    async def generate(self, request):
        self.calls.append(request.capability)
        return ModelResponse(json.dumps({"text": self.name}), self.name, "test", "stop")


class RoutedGatewayTests(unittest.TestCase):
    def request(self, capability):
        return ModelRequest(capability, (ModelMessage("user", "{}"),))

    def test_exact_role_route_overrides_default(self):
        default, dream = Gateway("small"), Gateway("dream")
        routed = RoutedModelGateway({"oneiros": dream}, default)
        self.assertEqual(
            asyncio.run(routed.generate(self.request("oneiros"))).resolved_model, "dream"
        )
        self.assertEqual(
            asyncio.run(routed.generate(self.request("murmur"))).resolved_model, "small"
        )
        self.assertEqual(dream.calls, ["oneiros"])
        self.assertEqual(default.calls, ["murmur"])
        with self.assertRaisesRegex(ValueError, "Unknown"):
            asyncio.run(routed.generate(self.request("intruder")))

    def test_unknown_and_incomplete_route_maps_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unknown"):
            RoutedModelGateway({"not-a-role": Gateway("bad")}, Gateway("default"))
        with self.assertRaisesRegex(ValueError, "missing"):
            RoutedModelGateway({"pathos": Gateway("voice")})
        complete = RoutedModelGateway({role: Gateway(role) for role in CAPABILITIES})
        self.assertIsNone(complete.default)

    def test_file_loader_resolves_secret_by_environment_name_without_inline_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "routes.json"
            path.write_text(
                json.dumps(
                    {
                        "default": {
                            "base_url": "http://127.0.0.1:11434/v1",
                            "model": "small-model",
                        },
                        "routes": {
                            "oneiros": {
                                "base_url": "http://127.0.0.1:11435/v1",
                                "model": "dream-model",
                                "api_key_env": "DREAM_MODEL_KEY",
                            }
                        },
                    }
                )
            )
            routed = routed_gateway_from_file(path, {"DREAM_MODEL_KEY": "secret"})
        self.assertEqual(routed.default.model, "small-model")
        self.assertEqual(routed.routes["oneiros"].model, "dream-model")
        self.assertEqual(routed.routes["oneiros"].api_key, "secret")

    def test_loader_rejects_inline_credentials_and_missing_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "routes.json"
            path.write_text(
                json.dumps(
                    {
                        "default": {
                            "base_url": "http://127.0.0.1:11434/v1",
                            "model": "model",
                            "api_key": "must-not-be-here",
                        }
                    }
                )
            )
            with self.assertRaises(ValueError):
                routed_gateway_from_file(path, {})
            path.write_text(
                json.dumps(
                    {
                        "default": {
                            "base_url": "http://127.0.0.1:11434/v1",
                            "model": "model",
                            "api_key_env": "MISSING_KEY",
                        }
                    }
                )
            )
            with self.assertRaisesRegex(ValueError, "unset"):
                routed_gateway_from_file(path, {})


if __name__ == "__main__":
    unittest.main()
