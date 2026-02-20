from __future__ import annotations

import json
import runpy
from pathlib import Path

import numpy as np


MODULE_PATH = "projects/rl-gridworld-qlearning/experiments/gridworld_qlearning.py"


def _load_module_symbols() -> dict[str, object]:
    return runpy.run_path(MODULE_PATH)


def test_q_learning_reproducible_with_fixed_seed() -> None:
    symbols = _load_module_symbols()
    cfg_cls = symbols["QLearningConfig"]
    train_fn = symbols["train_q_learning"]

    cfg = cfg_cls(seed=123, episodes=400)
    r1 = train_fn(cfg)
    r2 = train_fn(cfg)

    assert np.allclose(r1["q_table"], r2["q_table"])
    assert np.allclose(r1["episode_rewards"], r2["episode_rewards"])


def test_q_learning_meets_regression_thresholds() -> None:
    symbols = _load_module_symbols()
    cfg_cls = symbols["QLearningConfig"]
    train_fn = symbols["train_q_learning"]

    cfg = cfg_cls(seed=42, episodes=500)
    result = train_fn(cfg)
    metrics = result["metrics"]

    assert metrics["final_avg_reward"] > metrics["initial_avg_reward"] + 2.0
    assert metrics["success_rate_last_100"] >= 0.80
    assert metrics["greedy_steps"] <= 10


def test_q_learning_run_writes_artifacts(tmp_path: Path) -> None:
    symbols = _load_module_symbols()
    run_fn = symbols["run"]

    outputs = run_fn(output_dir=tmp_path / "artifacts")
    for path in outputs.values():
        assert Path(path).exists()

    summary = json.loads((tmp_path / "artifacts" / "summary.json").read_text(encoding="utf-8"))
    assert "metrics" in summary
    assert summary["metrics"]["success_rate_last_100"] >= 0.0
