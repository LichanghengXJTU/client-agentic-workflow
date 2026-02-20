from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np


ACTION_DELTAS = [(-1, 0), (0, 1), (1, 0), (0, -1)]


@dataclass
class QLearningConfig:
    size: int = 4
    episodes: int = 500
    max_steps: int = 40
    alpha: float = 0.2
    gamma: float = 0.95
    epsilon_start: float = 0.30
    epsilon_end: float = 0.05
    epsilon_decay: float = 0.995
    seed: int = 42


class Gridworld:
    def __init__(self, size: int = 4) -> None:
        self.size = size
        self.start = (0, 0)
        self.goal = (size - 1, size - 1)

    @property
    def num_states(self) -> int:
        return self.size * self.size

    @property
    def num_actions(self) -> int:
        return len(ACTION_DELTAS)

    def state_to_idx(self, state: tuple[int, int]) -> int:
        return state[0] * self.size + state[1]

    def idx_to_state(self, idx: int) -> tuple[int, int]:
        return (idx // self.size, idx % self.size)

    def reset(self) -> int:
        return self.state_to_idx(self.start)

    def step(self, state_idx: int, action: int) -> tuple[int, float, bool]:
        r, c = self.idx_to_state(state_idx)
        dr, dc = ACTION_DELTAS[action]
        nr = min(max(r + dr, 0), self.size - 1)
        nc = min(max(c + dc, 0), self.size - 1)
        nxt = self.state_to_idx((nr, nc))
        done = (nr, nc) == self.goal
        reward = 10.0 if done else -1.0
        return nxt, reward, done


def _epsilon_at(config: QLearningConfig, episode: int) -> float:
    decayed = config.epsilon_start * (config.epsilon_decay**episode)
    return max(config.epsilon_end, decayed)


def _choose_action(q: np.ndarray, state: int, epsilon: float, rng: np.random.Generator) -> int:
    if rng.random() < epsilon:
        return int(rng.integers(q.shape[1]))
    return int(np.argmax(q[state]))


def evaluate_greedy_policy(q: np.ndarray, env: Gridworld, max_steps: int) -> int:
    state = env.reset()
    for step in range(max_steps):
        action = int(np.argmax(q[state]))
        state, _, done = env.step(state, action)
        if done:
            return step + 1
    return max_steps + 1


def train_q_learning(config: QLearningConfig) -> dict[str, np.ndarray | float | int]:
    rng = np.random.default_rng(config.seed)
    env = Gridworld(size=config.size)
    q = np.zeros((env.num_states, env.num_actions), dtype=float)

    rewards = np.zeros(config.episodes, dtype=float)
    steps = np.zeros(config.episodes, dtype=int)
    success = np.zeros(config.episodes, dtype=int)

    for ep in range(config.episodes):
        state = env.reset()
        epsilon = _epsilon_at(config, ep)
        total_reward = 0.0

        for t in range(config.max_steps):
            action = _choose_action(q, state, epsilon, rng)
            nxt, reward, done = env.step(state, action)

            bootstrap = 0.0 if done else config.gamma * np.max(q[nxt])
            target = reward + bootstrap
            q[state, action] += config.alpha * (target - q[state, action])

            total_reward += reward
            state = nxt
            if done:
                success[ep] = 1
                steps[ep] = t + 1
                break
        else:
            steps[ep] = config.max_steps

        rewards[ep] = total_reward

    first_window = max(1, min(50, config.episodes // 2))
    last_window = max(1, min(50, config.episodes // 2))

    metrics = {
        "initial_avg_reward": float(np.mean(rewards[:first_window])),
        "final_avg_reward": float(np.mean(rewards[-last_window:])),
        "success_rate_last_100": float(np.mean(success[-100:])),
        "greedy_steps": int(evaluate_greedy_policy(q, env, config.max_steps)),
    }

    return {
        "q_table": q,
        "episode_rewards": rewards,
        "episode_steps": steps,
        "episode_success": success,
        "metrics": metrics,
    }


def save_artifacts(result: dict[str, np.ndarray | float | int], config: QLearningConfig, output_dir: str | Path) -> dict[str, str]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    q = result["q_table"]
    rewards = result["episode_rewards"]
    steps = result["episode_steps"]
    success = result["episode_success"]
    metrics = result["metrics"]

    np.save(out / "q_table.npy", q)

    with (out / "training_trace.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["episode", "reward", "steps", "success"])
        for i in range(len(rewards)):
            writer.writerow([i + 1, float(rewards[i]), int(steps[i]), int(success[i])])

    summary = {
        "config": asdict(config),
        "metrics": metrics,
    }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    report = "\n".join(
        [
            "# Gridworld Q-learning Report",
            "",
            "## Metrics",
            f"- initial_avg_reward: {metrics['initial_avg_reward']:.4f}",
            f"- final_avg_reward: {metrics['final_avg_reward']:.4f}",
            f"- success_rate_last_100: {metrics['success_rate_last_100']:.4f}",
            f"- greedy_steps: {metrics['greedy_steps']}",
        ]
    )
    (out / "report.md").write_text(report + "\n", encoding="utf-8")

    return {
        "q_table": str(out / "q_table.npy"),
        "trace": str(out / "training_trace.csv"),
        "summary": str(out / "summary.json"),
        "report": str(out / "report.md"),
    }


def run(output_dir: str | Path = "artifacts/experiments/rl-gridworld-qlearning", config: QLearningConfig | None = None) -> dict[str, str]:
    cfg = config or QLearningConfig()
    result = train_q_learning(cfg)
    return save_artifacts(result, cfg, output_dir)


def main() -> None:
    outputs = run()
    print(json.dumps(outputs, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
