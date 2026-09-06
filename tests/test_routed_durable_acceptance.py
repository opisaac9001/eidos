import tempfile
import unittest
from pathlib import Path

from eidos.adapters.durable_gateway import DurableModelGateway
from eidos.adapters.routed_gateway import RoutedModelGateway
from eidos.adapters.sqlite_jobs import SQLiteJobStore
from eidos.adapters.sqlite_store import SQLiteEventStore
from eidos.adapters.standin_gateway import StandInGateway
from eidos.application.cognition_supervisor import CognitionSupervisor
from eidos.application.life import Life


class RoutedDurableAcceptanceTests(unittest.TestCase):
    def test_week_combines_routing_durability_structured_world_work_and_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "routed-world.sqlite3"
            store = SQLiteEventStore(path)
            jobs = SQLiteJobStore(path)
            routed = RoutedModelGateway(
                {
                    "oneiros": StandInGateway(),
                    "moira_event": StandInGateway(),
                    "moira_expansion": StandInGateway(),
                },
                StandInGateway(),
            )

            def revision_for(aggregate):
                return len(store.read(aggregate))

            supervisor = CognitionSupervisor(jobs, routed, revision_for, worker_count=2)
            durable = DurableModelGateway(routed, jobs, revision_for, supervisor=supervisor)
            life = Life(store, durable, mode="routed-local-models")
            try:
                for _ in range(7):
                    life.advance(24)
                snapshot = life.snapshot()
            finally:
                durable.close()

            history = life.history()
            completed = jobs.list_jobs(1000)
            structured = [
                job for job in completed if job.capability in {"moira_event", "moira_expansion"}
            ]
            self.assertTrue(structured)
            self.assertTrue(all(job.status == "completed" for job in structured))
            self.assertTrue(all(job.result and job.result.startswith("{") for job in structured))
            self.assertTrue(all(job.resolved_model == "authored-stand-in-v1" for job in structured))
            self.assertTrue(any(event.kind == "world_event.accepted" for event in history))
            self.assertTrue(any(event.kind == "cognition.result_applied" for event in history))

            replay = Life(
                SQLiteEventStore(path),
                RoutedModelGateway({}, StandInGateway()),
                mode="routed-local-models",
            ).snapshot()
            self.assertEqual(snapshot, replay)


if __name__ == "__main__":
    unittest.main()
