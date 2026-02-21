# RL Project Math Strictness Override

- For Bellman/Q-learning equations, explicitly track state/action indices and transition dimensions at each step.
- Validate contraction proofs with both symbolic structure checks and numeric finite-MDP sampling.
- Mandatory checks for this project:
  1. Bellman operator contraction bound under sup norm.
  2. Q-learning sampled target consistency for alpha=1 update.
  3. Deterministic seed reproducibility for verification scripts.
- Any mismatch must report the exact first failing equation line.
