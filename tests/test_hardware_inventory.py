import unittest

from eidos.adapters.redfish import RedfishClient
from eidos.application.hardware_inventory import collect_redfish_inventory


class HardwareInventoryTests(unittest.TestCase):
    def test_client_refuses_plain_http_embedded_credentials_and_empty_secrets(self):
        for url, user, password in (
            ("http://idrac.local", "operator", "secret"),
            ("https://operator:secret@idrac.local", "operator", "secret"),
            ("https://idrac.local", "", "secret"),
            ("https://idrac.local", "operator", ""),
        ):
            with self.subTest(url=url, user=user):
                with self.assertRaises(ValueError):
                    RedfishClient(url, user, password)

    def test_collection_is_bounded_read_only_and_redacts_sensitive_fields(self):
        fixtures = {
            "/redfish/v1": {
                "Systems": {"@odata.id": "/redfish/v1/Systems"},
                "Chassis": {"@odata.id": "/redfish/v1/Chassis"},
            },
            "/redfish/v1/Systems": {
                "Members": [{"@odata.id": "/redfish/v1/Systems/System.Embedded.1"}]
            },
            "/redfish/v1/Systems/System.Embedded.1": {
                "Model": "PowerEdge T630",
                "Password": "must-not-leak",
                "Processors": {"@odata.id": "/redfish/v1/Systems/1/Processors"},
                "Memory": {"@odata.id": "/redfish/v1/Systems/1/Memory"},
                "PCIeDevices": [{"@odata.id": "/redfish/v1/Chassis/1/PCIeDevices/GPU1"}],
            },
            "/redfish/v1/Systems/1/Processors": {
                "Members": [{"@odata.id": "/redfish/v1/Systems/1/Processors/CPU1"}]
            },
            "/redfish/v1/Systems/1/Processors/CPU1": {"Model": "Xeon fixture"},
            "/redfish/v1/Systems/1/Memory": {"Members": []},
            "/redfish/v1/Chassis/1/PCIeDevices/GPU1": {
                "Model": "Tesla P40",
                "Manufacturer": "NVIDIA",
            },
            "/redfish/v1/Chassis": {"Members": []},
        }
        requested: list[str] = []

        def fetch(path: str):
            requested.append(path)
            return fixtures[path]

        report = collect_redfish_inventory(fetch, "idrac.local")
        self.assertTrue(report["read_only"])
        self.assertEqual(report["endpoint_host"], "idrac.local")
        self.assertIn("/redfish/v1/Systems/1/Processors/CPU1", report["resources"])
        self.assertEqual(
            report["resources"]["/redfish/v1/Chassis/1/PCIeDevices/GPU1"]["Model"],
            "Tesla P40",
        )
        system = report["resources"]["/redfish/v1/Systems/System.Embedded.1"]
        self.assertNotIn("Password", system)
        self.assertEqual(len(requested), len(set(requested)))

    def test_optional_unsupported_surfaces_are_reported_without_aborting(self):
        fixtures = {
            "/redfish/v1": {"Managers": {"@odata.id": "/redfish/v1/Managers"}},
            "/redfish/v1/Managers": {
                "Members": [{"@odata.id": "/redfish/v1/Managers/iDRAC.Embedded.1"}]
            },
            "/redfish/v1/Managers/iDRAC.Embedded.1": {
                "LogServices": {"@odata.id": "/redfish/v1/Managers/1/Logs"}
            },
        }

        def fetch(path: str):
            if path not in fixtures:
                raise OSError("unsupported")
            return fixtures[path]

        report = collect_redfish_inventory(fetch, "idrac.local")
        self.assertEqual(report["errors"]["/redfish/v1/Managers/1/Logs"], "OSError")


if __name__ == "__main__":
    unittest.main()
