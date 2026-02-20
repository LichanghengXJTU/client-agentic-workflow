# Q-learning and Bellman Optimality Relation

## Update rule
For one sampled transition \((s_t, a_t, r_t, s_{t+1})\), tabular Q-learning updates:

\[
Q_{t+1}(s_t, a_t) = (1 - \alpha_t)Q_t(s_t, a_t) + \alpha_t \left[r_t + \gamma \max_{a'} Q_t(s_{t+1}, a')\right].
\]

The bracketed term is a stochastic sample of the Bellman optimality backup target.

## Bellman optimality operator
Define

\[
(\mathcal{T}_* Q)(s,a) = \mathbb{E}\left[r(s,a,s') + \gamma \max_{a'} Q(s',a')\right].
\]

Q-learning is a stochastic approximation to the fixed-point equation:

\[
Q^* = \mathcal{T}_* Q^*.
\]

## Why convergence is expected in this project
This project uses a finite deterministic Gridworld and bounded rewards. Under sufficient exploration and Robbins-Monro style step-size conditions, tabular Q-learning converges to \(Q^*\). In practice here, we use a fixed small step size and a decaying \(\epsilon\)-greedy policy; we verify empirical improvement and policy quality with reproducible tests.

## Runnable verification
See `projects/rl-gridworld-qlearning/derivations/q_learning_bellman_check.py`.
The script checks two properties on a finite MDP:
1. Bellman optimality operator is a \(\gamma\)-contraction under sup norm.
2. A one-step update with \(\alpha=1\) matches the sampled Bellman target exactly.
