# Copyright (c) 2026 Brian Pursley
# SPDX-License-Identifier: MIT
"""Check sorting, size, packed depth and optional symmetry in catalog JSON files.

Requires Python 3.7+ and the cadical executable on PATH.
"""

import argparse
import json
from pathlib import Path
import subprocess
import sys


def unique_fields(items):
    """Reject repeated JSON field names so the network has one interpretation."""
    fields = {}
    for name, value in items:
        if name in fields:
            raise ValueError(f"duplicate JSON field: {name}")
        fields[name] = value
    return fields


def verify(network):
    if not isinstance(network, dict):
        raise ValueError("expected a JSON object describing a network")
    n, size, depth = network.get("N"), network.get("L"), network.get("D")
    if any(type(v) is not int for v in (n, size, depth)) or n < 1:
        raise ValueError("expected integers N, L and D with N >= 1")
    pairs = network.get("nw")
    if not isinstance(pairs, list):
        raise ValueError("expected a list of comparators in nw")
    if len(pairs) != size:
        raise ValueError("comparator count disagrees with L")
    # The minimum can start on any wire and must reach wire 0. Connecting
    # all n wires takes at least n - 1 comparators.
    if size < n - 1:
        raise ValueError(f"too few comparators to connect {n} wires")

    check_symmetry = "symmetric" in network
    if check_symmetry and type(network["symmetric"]) is not bool:
        raise ValueError("symmetric must be a JSON boolean")

    last_layer = [0] * n
    layered_pairs = set()
    for i, pair in enumerate(pairs):
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            raise ValueError(f"comparator {i} must have two wire indices")
        a, b = pair
        if type(a) is not int or type(b) is not int or not 0 <= a < b < n:
            raise ValueError(f"invalid wire pair at comparator {i}: {pair}")
        # A comparator must follow the last comparison on each of its two wires.
        layer = 1 + max(last_layer[a], last_layer[b])
        last_layer[a] = last_layer[b] = layer
        if check_symmetry:
            layered_pairs.add((layer, a, b))
    packed_depth = max(last_layer)
    if packed_depth != depth:
        raise ValueError(f"packed depth is {packed_depth}, file declares {depth}")

    if check_symmetry:
        symmetric = all(
            (layer, n - 1 - b, n - 1 - a) in layered_pairs
            for layer, a, b in layered_pairs
        )
        if network["symmetric"] != symmetric:
            raise ValueError(f"symmetric should be {json.dumps(symmetric)} for the packed layers")

    check_sorting(n, pairs)
    return n, size, depth


def counterexample_cnf(n, pairs):
    """Encode a binary input with an unsorted output in DIMACS CNF."""
    # wires[i] is the Boolean variable for the current value on wire i.
    wires = list(range(1, n + 1))
    variables = n
    clauses = []

    # Each clause is an OR of literals. A negative literal negates its variable.
    # A satisfying assignment must make every clause true.
    for a, b in pairs:
        x, y = wires[a], wires[b]
        low, high = variables + 1, variables + 2
        variables += 2
        # For bits, low = x AND y and high = x OR y.
        clauses.extend([(-low, x), (-low, y), (low, -x, -y)])
        clauses.extend([(high, -x), (high, -y), (-high, x, y)])
        wires[a], wires[b] = low, high

    # Selecting a pair forces its outputs to (1, 0). One such pair suffices
    # to witness an unsorted output, so at least one selector must be true.
    inversions = []
    for left, right in zip(wires, wires[1:]):
        variables += 1
        inversion = variables
        inversions.append(inversion)
        clauses.extend([(-inversion, left), (-inversion, -right)])
    clauses.append(inversions)  # For one wire this is an unsatisfiable empty clause.

    lines = [f"p cnf {variables} {len(clauses)}"]
    for clause in clauses:
        lines.append(" ".join(str(value) for value in (*clause, 0)))
    return "\n".join(lines) + "\n"


def check_sorting(n, pairs):
    """Ask CaDiCaL whether any binary input produces an unsorted output."""
    try:
        result = subprocess.run(
            ["cadical", "-q", "-n"], input=counterexample_cnf(n, pairs),
            capture_output=True, text=True,
        )
    except FileNotFoundError as error:
        raise RuntimeError("CaDiCaL is required. Install cadical and put it on PATH.") from error

    # CaDiCaL returns 20 for UNSAT and 10 for SAT. Only UNSAT proves sorting.
    statuses = [line for line in result.stdout.splitlines() if line.startswith("s ")]
    if result.returncode == 20 and statuses == ["s UNSATISFIABLE"]:
        return
    if result.returncode == 10 and statuses == ["s SATISFIABLE"]:
        raise ValueError("some binary input produces an unsorted output")
    detail = result.stderr.strip() or result.stdout.strip() or "no solver output"
    raise RuntimeError(f"CaDiCaL did not confirm sorting (exit {result.returncode}): {detail}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", type=Path, nargs="+", help="one or more network JSON files")
    failed = False
    for path in parser.parse_args().files:
        try:
            network = json.loads(path.read_bytes(), object_pairs_hook=unique_fields)
            n, size, depth = verify(network)
        except (OSError, ValueError, RuntimeError) as error:
            print(f"{path}: {error}", file=sys.stderr)
            failed = True
        else:
            print(f"{path}: verified {n} inputs, {size} comparators, {depth} layers", flush=True)
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
