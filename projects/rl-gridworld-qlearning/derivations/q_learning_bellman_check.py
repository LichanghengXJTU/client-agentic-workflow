from __future__ import annotations

import numpy as np


def bellman_optimality_operator(q: np.ndarray, r: np.ndarray, p: np.ndarray, gamma: float) -> np.ndarray:
    # q shape: [S, A], r shape: [S, A], p shape: [S, A, S]
    v = np.max(q, axis=1)
    return r + gamma * np.einsum("sas,s->sa", p, v)


def contraction_check(seed: int = 7) -> None:
    rng = np.random.default_rng(seed)
    num_states = 5
    num_actions = 3
    gamma = 0.9

    # Random row-stochastic transition tensor
    p = rng.uniform(size=(num_states, num_actions, num_states))
    p = p / np.sum(p, axis=2, keepdims=True)
    r = rng.uniform(low=-1.0, high=1.0, size=(num_states, num_actions))

    q1 = rng.normal(size=(num_states, num_actions))
    q2 = rng.normal(size=(num_states, num_actions))

    t1 = bellman_optimality_operator(q1, r, p, gamma)
    t2 = bellman_optimality_operator(q2, r, p, gamma)

    lhs = np.max(np.abs(t1 - t2))
    rhs = gamma * np.max(np.abs(q1 - q2)) + 1e-12
    assert lhs <= rhs, f"Contraction violated: lhs={lhs}, rhs={rhs}"


def sampled_update_matches_target() -> None:
    gamma = 0.95
    q = np.array(
        [
            [0.5, -0.2, 0.1],
            [1.2, 0.0, 0.8],
            [0.3, 0.9, -0.1],
        ],
        dtype=float,
    )

    s = 0
    a = 2
    r = 1.5
    s_next = 1
    alpha = 1.0

    target = r + gamma * np.max(q[s_next])
    updated = q.copy()
    updated[s, a] = (1.0 - alpha) * updated[s, a] + alpha * target

    assert np.isclose(updated[s, a], target), "alpha=1 update must equal sampled Bellman target"


def main() -> None:
    contraction_check()
    sampled_update_matches_target()
    print("q_learning_bellman_check passed")


if __name__ == "__main__":
    main()
