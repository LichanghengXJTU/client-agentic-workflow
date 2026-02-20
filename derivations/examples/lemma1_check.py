from __future__ import annotations

from sympy import expand, simplify, symbols


def main() -> None:
    a, b = symbols("a b")
    lhs = expand((a + b) ** 2)
    rhs = a**2 + 2 * a * b + b**2
    if simplify(lhs - rhs) != 0:
        raise SystemExit("lemma1 verification failed")
    print("lemma1 verification passed")


if __name__ == "__main__":
    main()
