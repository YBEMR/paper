"""Explicit candidate DAG rules; no task sampling, scheduling or thermal work.

The rules below are implementation proposals, not automatically approved
scientific settings.  Every setting must be supplied by the caller.
"""

from collections import deque
from fractions import Fraction
import hashlib
import json
import math


class TopologyError(ValueError):
    def __init__(self, code, **details):
        self.code = code
        self.details = details
        super().__init__(code)


def _require(condition, code, **details):
    if not condition:
        raise TopologyError(code, **details)


def _settings(settings):
    literals = {
        "algorithm_version": "layered-forward-v1",
        "layer_rule": "ceil_sqrt_balanced",
        "output_rule": "all_last_layer",
        "edge_target_rounding": "half_up",
        "edge_cap_rule": "max_bipartite_degree_capacity",
        "small_two_node_rule": "chain",
        "branch_rule": "first_diamond_then_tail_chain",
        "reject_total_reachability_order": True,
        "reject_branch_template": True,
    }
    expected = set(literals) | {
        "edge_target_multiplier", "max_indegree", "max_outdegree", "max_attempts"}
    _require(isinstance(settings, dict) and set(settings) == expected,
             "EXPLICIT_TOPOLOGY_SETTINGS_REQUIRED", expected=sorted(expected))
    for key, value in literals.items():
        _require(type(settings[key]) is type(value) and settings[key] == value,
                 "UNSUPPORTED_TOPOLOGY_RULE", field=key)
    for key in ("max_indegree", "max_outdegree", "max_attempts"):
        _require(type(settings[key]) is int and settings[key] >= 1,
                 "POSITIVE_INTEGER_REQUIRED", field=key)
    value = settings["edge_target_multiplier"]
    _require(type(value) in (str, int), "EXACT_EDGE_MULTIPLIER_REQUIRED")
    try:
        multiplier = Fraction(value)
    except (TypeError, ValueError, ZeroDivisionError) as error:
        raise TopologyError("INVALID_EDGE_MULTIPLIER") from error
    _require(multiplier > 0, "NONPOSITIVE_EDGE_MULTIPLIER")
    return multiplier


def _nodes(nodes):
    _require(isinstance(nodes, list) and len(nodes) >= 2 and
             all(isinstance(node, str) and node.strip() for node in nodes),
             "AT_LEAST_TWO_DISTINCT_NODES_REQUIRED")
    _require(len(set(nodes)) == len(nodes), "DUPLICATE_NODE_ID")
    return list(nodes)


def _rank(key, *parts):
    payload = json.dumps([key, *parts], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _branch_edges(nodes):
    if len(nodes) < 4:
        return [(nodes[i], nodes[i + 1]) for i in range(len(nodes) - 1)]
    return [(nodes[0], nodes[1]), (nodes[0], nodes[2]),
            (nodes[1], nodes[3]), (nodes[2], nodes[3])] + [
                (nodes[i], nodes[i + 1]) for i in range(3, len(nodes) - 1)]


def validate_graph(nodes, edges, required_outputs, *, max_indegree,
                   max_outdegree, layers, require_nonchain, forbidden_edges):
    """Independently check graph semantics, including reachability (not edge count).

    Last-layer nodes are all required outputs.  A request completes only when
    all required outputs finish; no virtual zero-work node is introduced.
    ``layers=None`` checks serial/branch graphs without imposing random layers.
    """
    nodes = _nodes(nodes)
    _require(isinstance(edges, list) and all(isinstance(e, (list, tuple)) and
             len(e) == 2 and all(isinstance(v, str) for v in e) for e in edges),
             "INVALID_EDGE_LIST")
    pairs = [tuple(edge) for edge in edges]
    _require(len(set(pairs)) == len(pairs), "DUPLICATE_EDGE")
    _require(isinstance(required_outputs, list) and bool(required_outputs) and
             len(set(required_outputs)) == len(required_outputs) and
             set(required_outputs) <= set(nodes), "INVALID_REQUIRED_OUTPUTS")
    successors = {node: [] for node in nodes}
    indegree = {node: 0 for node in nodes}
    for left, right in pairs:
        _require(left in successors and right in successors and left != right,
                 "INVALID_EDGE_ENDPOINT")
        successors[left].append(right)
        indegree[right] += 1
    _require(max(indegree.values()) <= max_indegree and
             max(map(len, successors.values())) <= max_outdegree,
             "DEGREE_LIMIT_EXCEEDED")
    remaining = dict(indegree)
    queue = deque(node for node in nodes if remaining[node] == 0)
    order = []
    while queue:
        node = queue.popleft()
        order.append(node)
        for nxt in successors[node]:
            remaining[nxt] -= 1
            if remaining[nxt] == 0:
                queue.append(nxt)
    _require(len(order) == len(nodes), "CYCLIC_GRAPH")
    _require(all(indegree[node] + len(successors[node]) > 0 for node in nodes),
             "ISOLATED_NODE")
    sinks = {node for node in nodes if not successors[node]}
    _require(set(required_outputs) == sinks, "REQUIRED_OUTPUTS_MUST_BE_ALL_SINKS")
    reachable = {}
    for node in reversed(order):
        reachable[node] = set(successors[node])
        for nxt in successors[node]:
            reachable[node].update(reachable[nxt])
    _require(all(node in sinks or bool(reachable[node] & sinks) for node in nodes),
             "NODE_CANNOT_REACH_REQUIRED_OUTPUT")
    if layers is not None:
        _require(isinstance(layers, list) and bool(layers) and
                 all(isinstance(layer, list) and layer for layer in layers),
                 "INVALID_LAYERS")
        flat = [node for layer in layers for node in layer]
        _require(len(flat) == len(nodes) and set(flat) == set(nodes),
                 "LAYER_NODE_COVERAGE")
        which = {node: i for i, layer in enumerate(layers) for node in layer}
        _require(all(which[left] < which[right] for left, right in pairs),
                 "NONFORWARD_LAYER_EDGE")
        _require(sinks == set(layers[-1]), "OUTPUT_LAYER_MISMATCH")
    incomparable = [[left, right] for i, left in enumerate(nodes)
                    for right in nodes[i + 1:]
                    if right not in reachable[left] and left not in reachable[right]]
    if require_nonchain:
        _require(bool(incomparable), "REACHABILITY_IS_TOTAL_ORDER")
    if forbidden_edges is not None:
        _require(set(pairs) != {tuple(e) for e in forbidden_edges},
                 "IDENTICAL_BRANCH_TEMPLATE")
    return {"state": "GRAPH_VALID", "node_count": len(nodes), "edge_count": len(pairs),
            "required_outputs": sorted(sinks), "incomparable_pairs": incomparable,
            "topological_order": order, "maximum_indegree": max(indegree.values()),
            "maximum_outdegree": max(map(len, successors.values()))}


def _degree_capacity(nodes, candidates, max_in, max_out):
    """Exact max-cardinality degree-feasible edge set by integral bipartite flow.

    One left copy controls each node's outdegree; one right copy controls its
    indegree.  Candidate arcs have capacity one.  This computes the *degree and
    layer* capacity, not existence of a connected/output-complete graph.  The
    latter is checked independently for every generated attempt.
    """
    size = len(nodes)
    source, sink = 2 * size, 2 * size + 1
    residual = [dict() for _ in range(2 * size + 2)]

    def arc(left, right, capacity):
        residual[left][right] = capacity
        residual[right].setdefault(left, 0)

    indices = {node: i for i, node in enumerate(nodes)}
    for i in range(size):
        arc(source, i, max_out)
        arc(size + i, sink, max_in)
    for left, right in candidates:
        arc(indices[left], size + indices[right], 1)
    flow = 0
    while True:
        previous = {source: None}
        queue = deque([source])
        while queue and sink not in previous:
            left = queue.popleft()
            for right in sorted(residual[left]):
                if residual[left][right] > 0 and right not in previous:
                    previous[right] = left
                    queue.append(right)
        if sink not in previous:
            return flow
        amount, right = size * max(max_in, max_out), sink
        while right != source:
            left = previous[right]
            amount = min(amount, residual[left][right])
            right = left
        right = sink
        while right != source:
            left = previous[right]
            residual[left][right] -= amount
            residual[right][left] += amount
            right = left
        flow += amount


def make_topology(nodes, kind, *, key, settings):
    """Return an explicit candidate graph and the full bounded-attempt trace."""
    nodes = _nodes(nodes)
    multiplier = _settings(settings)
    _require(kind in ("serial", "branch_join", "layered"), "UNKNOWN_TOPOLOGY")
    _require(isinstance(key, str) and bool(key), "EXPLICIT_TOPOLOGY_KEY_REQUIRED")
    trace = {"rule_status": "CANDIDATE_NOT_SCIENTIFICALLY_FROZEN", "key": key,
             "settings": dict(settings), "attempts": []}
    max_in, max_out = settings["max_indegree"], settings["max_outdegree"]
    if kind != "layered" or len(nodes) == 2:
        edges = (_branch_edges(nodes) if kind == "branch_join" else
                 [(nodes[i], nodes[i + 1]) for i in range(len(nodes) - 1)])
        if kind == "layered":
            trace["small_graph_exception"] = "TWO_NODE_CHAIN"
        check = validate_graph(nodes, edges, [nodes[-1]], max_indegree=max_in,
                               max_outdegree=max_out, layers=None,
                               require_nonchain=False, forbidden_edges=None)
        trace["validation"] = check
        return {"edges": [list(e) for e in sorted(edges)],
                "required_outputs": [nodes[-1]], "trace": trace}
    _require(len(nodes) >= 4, "LAYERED_THREE_NODE_RULE_NOT_DECLARED")
    layer_count = math.isqrt(len(nodes))
    if layer_count * layer_count < len(nodes):
        layer_count += 1
    quotient, remainder = divmod(len(nodes), layer_count)
    widths = [quotient + int(i < remainder) for i in range(layer_count)]
    target_value = multiplier * (len(nodes) - 1)
    raw_target = (2 * target_value.numerator + target_value.denominator) // (
        2 * target_value.denominator)
    trace.update({"layer_widths": widths, "raw_edge_target": raw_target,
                  "capacity_meaning": "layer_forward_and_degree_only"})
    capacity = None
    for attempt in range(settings["max_attempts"]):
        sequence = sorted(nodes, key=lambda node: (_rank(key, "layers", attempt, node), node))
        layers, at = [], 0
        for width in widths:
            layers.append(sequence[at:at + width])
            at += width
        candidates = [(left, right) for i, layer in enumerate(layers)
                      for later in layers[i + 1:] for left in layer for right in later]
        if capacity is None:
            capacity = _degree_capacity(nodes, candidates, max_in, max_out)
            trace["degree_layer_capacity"] = capacity
            trace["edge_target"] = min(raw_target, capacity)
            trace["capacity_capped"] = raw_target > capacity
        target = trace["edge_target"]
        edges = set()
        incoming, outgoing = dict.fromkeys(nodes, 0), dict.fromkeys(nodes, 0)
        record = {"attempt": attempt, "layers": layers}

        def add(left, right):
            if (left, right) in edges:
                return True
            if incoming[right] >= max_in or outgoing[left] >= max_out:
                return False
            edges.add((left, right))
            incoming[right] += 1
            outgoing[left] += 1
            return True

        # Balanced layers have non-increasing widths.  Cover both sides of
        # each adjacent pair to make every node reach a declared final output.
        backbone_ok = True
        for i in range(len(layers) - 1):
            lefts = sorted(layers[i], key=lambda node: (_rank(key, "backbone_left", attempt, i, node), node))
            rights = sorted(layers[i + 1], key=lambda node: (_rank(key, "backbone_right", attempt, i, node), node))
            for j, left in enumerate(lefts):
                if not add(left, rights[j % len(rights)]):
                    backbone_ok = False
        record["backbone_edges"] = [list(e) for e in sorted(edges)]
        if not backbone_ok or len(edges) > target:
            record.update({"state": "REJECTED", "reason": "BACKBONE_TARGET_OR_DEGREE_CONFLICT"})
            trace["attempts"].append(record)
            continue
        for left, right in sorted(candidates, key=lambda e: (_rank(key, "edge", attempt, *e), e)):
            if len(edges) == target:
                break
            add(left, right)
        record["edges"] = [list(e) for e in sorted(edges)]
        if len(edges) != target:
            record.update({"state": "REJECTED", "reason": "GREEDY_TARGET_UNREACHED"})
            trace["attempts"].append(record)
            continue
        try:
            check = validate_graph(nodes, record["edges"], layers[-1],
                                   max_indegree=max_in, max_outdegree=max_out,
                                   layers=layers, require_nonchain=True,
                                   forbidden_edges=[list(e) for e in _branch_edges(nodes)])
        except TopologyError as error:
            record.update({"state": "REJECTED", "reason": error.code, "details": error.details})
            trace["attempts"].append(record)
            continue
        record["state"] = "ACCEPTED"
        trace["attempts"].append(record)
        trace["validation"] = check
        return {"edges": record["edges"], "required_outputs": sorted(layers[-1]), "trace": trace}
    raise TopologyError("BOUNDED_TOPOLOGY_ATTEMPTS_EXHAUSTED", trace=trace)
