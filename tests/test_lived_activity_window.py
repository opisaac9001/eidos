import importlib.util
from datetime import datetime
from pathlib import Path


def test_completion_precedes_the_next_departure(tmp_path):
    module_path = Path(__file__).resolve().parents[1] / "infra/lived_day_trial.py"
    spec = importlib.util.spec_from_file_location("lived_day_trial", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    life = module.seed(tmp_path / "life.sqlite3")
    life.advance(5 / 60)
    life.advance(25 / 60)
    context = module.context(life, "Are the dishes finished?")
    assert context["ongoing_activities"][0]["outcome"] == "completed"
    assert context["journey"] is not None
    history = life.history()
    completed = next(i for i, e in enumerate(history) if e.kind == "schedule.completed")
    departed = next(i for i, e in enumerate(history) if e.kind == "pathos.travel_started")
    assert completed < departed
    assert datetime.fromisoformat(
        str(history[completed].payload["simulated_at"])
    ) <= datetime.fromisoformat(str(history[departed].payload["simulated_at"]))


def test_fine_and_coarse_complete_the_same_two_activities(tmp_path):
    module_path = Path(__file__).resolve().parents[1] / "infra/lived_day_trial.py"
    spec = importlib.util.spec_from_file_location("lived_day_trial", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    coarse = module.seed(tmp_path / "coarse.sqlite3")
    fine = module.seed(tmp_path / "fine.sqlite3")
    coarse.advance(1.5)
    for _ in range(90):
        fine.advance(1 / 60)
    for life in (coarse, fine):
        assert len([e for e in life.history() if e.kind == "schedule.completed"]) == 2
        assert not any(e.kind == "schedule.interrupted" for e in life.history())
