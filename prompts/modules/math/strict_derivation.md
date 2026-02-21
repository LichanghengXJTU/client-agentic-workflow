# Strict Math Protocol

- Do not skip algebraic or index transitions in derivation assets.
- Explicitly validate index bounds and subscript consistency at each transformation stage.
- Provide dual verification for key formulas:
  1. Symbolic verification (e.g., SymPy simplify/expand/equality check)
  2. Numeric or boundary/invariant verification (randomized checks + edge cases)
- If mismatch appears, stop and report the first inconsistent step.
- Output format:
  - Main body: final theorem/lemma conclusion and minimal key equations.
  - Appendix: full line-by-line derivation and re-check records.
