# Re-Verification Loop

- For high-risk formulas, run repeated validation with at least two seeds or parameter sets.
- Include a short error taxonomy: index mismatch, sign error, domain violation, boundary violation.
- If verification fails, keep the failed attempt in logs and present corrected derivation separately.
- Never overwrite failed evidence with only successful reruns.
