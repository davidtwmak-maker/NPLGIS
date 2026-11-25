"""Regression guard: the geocode matcher's token score must be computed
before the distance gate that reads it.

THE BUG
    `choose()` scored how well a gazetteer hit's own name matched the
    shop's name (token_q), then applied a distance gate that READ
    token_q to decide whether a far hit could still be the right
    building:

        if d > MAX_M * 1.5:
            if not (token_q >= 90 and htype == "B"):
                continue

    In an intermediate version of the file the score was computed
    AFTER that gate, so the gate read a name that had never been
    assigned:

        UnboundLocalError: cannot access local variable 'token_q'

    It crashed the run rather than corrupting it, which is the better
    of the two outcomes - but it crashed a 205-shop geocode part way
    through, and a run that dies mid-way leaves the previous output
    file in place with no sign that this one produced nothing.

THE RULE
    Every name a function reads must be assigned on every path that
    reaches the read. The static check below walks the function's AST
    and asserts that each assignment precedes each read in the source
    order, which is the conservative direction for a straight-line
    loop body.

RUN
    python3 scripts/tcg-stores/check_token_order.py
"""
import ast
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TARGET = HERE / "geocode_shops.py"

# (function name, variable) pairs that must be assigned before use.
PAIRS = [("choose", "token_q"), ("choose", "token_hit")]


def check(path):
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    problems = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for fn, var in PAIRS:
            if node.name != fn:
                continue
            assign_lines = []
            read_lines = []
            for n in ast.walk(node):
                if isinstance(n, ast.Name) and n.id == var:
                    if isinstance(n.ctx, ast.Store):
                        assign_lines.append(n.lineno)
                    else:
                        read_lines.append(n.lineno)
            if not assign_lines:
                problems.append(
                    f"{fn}(): {var} is read but never assigned")
                continue
            first_assign = min(assign_lines)
            # A read that precedes EVERY assignment is the bug: on that
            # path the variable has no value yet.
            early = [r for r in read_lines if r < first_assign]
            if early:
                problems.append(
                    f"{fn}(): {var} is read at line {min(early)} but first "
                    f"assigned at line {first_assign}")
            else:
                print(f"  {fn}(): {var} first assigned at line {first_assign}, "
                      f"read at {sorted(read_lines)}")
    return problems


def main():
    if not TARGET.exists():
        print(f"  {TARGET} not found")
        return 1
    print(f"  checking {TARGET.name}")
    problems = check(TARGET)
    print()
    if problems:
        print("BROKEN BUILD:")
        for p in problems:
            print(f"  {p}")
        return 1
    print("OK: every token is assigned before it is read.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
