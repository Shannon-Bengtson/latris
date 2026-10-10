"""Graph analysis algorithms for CLD and DAG formalisms.

Pure functions — no file I/O, no commits.  Callers load the substrate
and pass it in.  Each function works on edge lists and optional attribute
data, never on file paths.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal, Protocol, TypeVar

# ── Protocols ────────────────────────────────────────────────────────────


class _HasDirection(Protocol):
    id: str
    from_id: str
    to_id: str


class _HasId(Protocol):
    id: str


class _HasKind(Protocol):
    kind: str


_EdgeT = TypeVar("_EdgeT", bound=_HasKind)


def causal_edges(edges: Iterable[_EdgeT]) -> list[_EdgeT]:
    """Filter to edges representing causal mechanisms.

    Loop counts, centrality, and acyclicity checks must use this.
    Non-causal kinds (decision_rule, governance, flow, support, ...)
    represent policy, accountability, or information availability —
    they look like arrows in prose but are not feedback-bearing
    mechanism. Counting them as such was the capability-run inflation
    bug the AI interrogation layer is built to fix.
    """
    return [e for e in edges if e.kind == "causal"]


# ── Result dataclasses ───────────────────────────────────────────────────


@dataclass(frozen=True)
class Loop:
    """An elementary circuit in the graph."""

    node_ids: tuple[str, ...]
    edge_ids: tuple[str, ...]
    classification: Literal["R", "B", "unknown"] = "unknown"


@dataclass(frozen=True)
class PropagationEffect:
    """Qualitative effect at one node during polarity propagation."""

    entity_id: str
    effect: Literal["+", "-", "ambiguous"]
    paths_positive: int = 0
    paths_negative: int = 0


@dataclass(frozen=True)
class CentralityResult:
    """Centrality metrics for a single entity."""

    entity_id: str
    degree_in: int
    degree_out: int
    degree_total: int
    betweenness: float


@dataclass(frozen=True)
class LoopParticipation:
    """Loop membership counts for a single entity."""

    entity_id: str
    loop_count: int
    reinforcing_count: int
    balancing_count: int


@dataclass(frozen=True)
class PathNode:
    """A node on a path with its structural classification."""

    entity_id: str
    classification: Literal["chain", "fork", "collider", "endpoint"]


@dataclass(frozen=True)
class GraphPath:
    """An undirected path between two nodes with structural info."""

    nodes: tuple[PathNode, ...]
    is_directed: bool  # True if all edges point in the same direction


# ── Helpers ──────────────────────────────────────────────────────────────


def _build_adj(edges: list[_HasDirection]) -> dict[str, list[tuple[str, str]]]:
    """Build adjacency list: node → [(neighbour, edge_id), ...]."""
    adj: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for e in edges:
        adj[e.from_id].append((e.to_id, e.id))
    return adj


def _build_edge_lookup(edges: list[_HasDirection]) -> dict[tuple[str, str], str]:
    """Build (from_id, to_id) → edge_id lookup."""
    lookup: dict[tuple[str, str], str] = {}
    for e in edges:
        lookup[(e.from_id, e.to_id)] = e.id
    return lookup


def _all_nodes(edges: list[_HasDirection]) -> set[str]:
    """Collect all node IDs referenced by edges."""
    nodes: set[str] = set()
    for e in edges:
        nodes.add(e.from_id)
        nodes.add(e.to_id)
    return nodes


def weakly_connected_components(
    node_ids: list[str], edges: list[_HasDirection]
) -> list[set[str]]:
    """Connected components over the UNDIRECTED projection of the graph.

    Edge direction is ignored. Isolated nodes (no incident edge) come back
    as singleton components, so this doubles as orphan detection: a single
    returned component means the graph is weakly connected with no orphans.
    """
    adj: dict[str, set[str]] = defaultdict(set)
    for e in edges:
        adj[e.from_id].add(e.to_id)
        adj[e.to_id].add(e.from_id)

    seen: set[str] = set()
    components: list[set[str]] = []
    for start in node_ids:
        if start in seen:
            continue
        comp: set[str] = set()
        stack = [start]
        while stack:
            n = stack.pop()
            if n in seen:
                continue
            seen.add(n)
            comp.add(n)
            stack.extend(nb for nb in adj[n] if nb not in seen)
        components.append(comp)
    return components


# ═══════════════════════════════════════════════════════════════════════
# CLD ANALYSIS
# ═══════════════════════════════════════════════════════════════════════


def find_all_loops(edges: list[_HasDirection]) -> list[Loop]:
    """Find all elementary circuits using Johnson's algorithm.

    Based on Donald B. Johnson, "Finding all the elementary circuits
    of a directed graph", SIAM J. Computing, 4(1), 1975, pp. 77–84.

    Returns loops with classification="unknown" — call classify_loop
    to assign R/B based on polarity.
    """
    # Build adjacency as node → [node, ...]
    adj: dict[str, list[str]] = defaultdict(list)
    for e in edges:
        adj[e.from_id].append(e.to_id)

    edge_lookup = _build_edge_lookup(edges)
    nodes = sorted(_all_nodes(edges))
    result: list[Loop] = []

    # Johnson's algorithm
    def _unblock(u: str) -> None:
        blocked_set.discard(u)
        while b_lists[u]:
            w = b_lists[u].pop()
            if w in blocked_set:
                _unblock(w)

    def _circuit(v: str, s: str) -> bool:
        found = False
        stack.append(v)
        blocked_set.add(v)

        for w in adj.get(v, []):
            if w not in node_subset:
                continue
            if w == s:
                # Found a circuit: stack contains the cycle path
                cycle_nodes = tuple(stack)
                cycle_edges: list[str] = []
                for i in range(len(cycle_nodes)):
                    from_n = cycle_nodes[i]
                    to_n = cycle_nodes[(i + 1) % len(cycle_nodes)]
                    eid = edge_lookup.get((from_n, to_n), "")
                    cycle_edges.append(eid)
                result.append(
                    Loop(
                        node_ids=cycle_nodes,
                        edge_ids=tuple(cycle_edges),
                    )
                )
                found = True
            elif w not in blocked_set:
                if _circuit(w, s):
                    found = True

        if found:
            _unblock(v)
        else:
            for w in adj.get(v, []):
                if w in node_subset and v not in b_lists[w]:
                    b_lists[w].add(v)

        stack.pop()
        return found

    for i, s in enumerate(nodes):
        # Only consider the subgraph induced by nodes[i:]
        node_subset = set(nodes[i:])
        blocked_set: set[str] = set()
        b_lists: dict[str, set[str]] = defaultdict(set)
        stack: list[str] = []
        _circuit(s, s)

    return result


def classify_loop(
    loop: Loop,
    polarity_map: dict[str, str],
) -> Loop:
    """Classify a loop as Reinforcing (R) or Balancing (B).

    A loop is Balancing if it contains an odd number of negative ("−")
    edges; Reinforcing if the count is even (including zero).  If any
    edge is missing polarity OR carries the ambiguous polarity "~",
    classification is "unknown" — an ambiguous edge cannot contribute a
    determinate sign to the loop's net effect.
    """
    neg_count = 0
    for eid in loop.edge_ids:
        pol = polarity_map.get(eid)
        if pol is None or pol == "~":
            return Loop(
                node_ids=loop.node_ids,
                edge_ids=loop.edge_ids,
                classification="unknown",
            )
        if pol == "-":
            neg_count += 1

    classification: Literal["R", "B"] = "B" if neg_count % 2 == 1 else "R"
    return Loop(
        node_ids=loop.node_ids,
        edge_ids=loop.edge_ids,
        classification=classification,
    )


def propagate_polarity(
    from_id: str,
    edges: list[_HasDirection],
    polarity_map: dict[str, str],
) -> list[PropagationEffect]:
    """Trace qualitative effect from a variable through the graph.

    Follows directed edges downstream, composing polarity along each
    path.  If multiple paths reach the same node with conflicting net
    effects, the effect is "ambiguous".

    Returns one PropagationEffect per reachable node (excluding from_id).
    """
    adj = _build_adj(edges)

    # For each reachable node, track counts of positive and negative paths
    pos_paths: dict[str, int] = defaultdict(int)
    neg_paths: dict[str, int] = defaultdict(int)

    # BFS with sign tracking
    # Queue: (current_node, cumulative_sign)  where sign is +1 or -1
    queue: list[tuple[str, int]] = [(from_id, 1)]  # start with positive

    # Use BFS but track all paths (allow revisiting via different edges)
    # To avoid infinite loops in cyclic graphs, track visited (node, sign) pairs
    seen: set[tuple[str, int]] = {(from_id, 1)}

    while queue:
        current, current_sign = queue.pop(0)
        for neighbour, eid in adj.get(current, []):
            pol = polarity_map.get(eid)
            if pol is None or pol == "~":
                # Unknown or ambiguous polarity — can't propagate a
                # determinate sign through this edge.
                continue
            edge_sign = 1 if pol == "+" else -1
            next_sign = current_sign * edge_sign

            if next_sign == 1:
                pos_paths[neighbour] += 1
            else:
                neg_paths[neighbour] += 1

            state = (neighbour, next_sign)
            if state not in seen:
                seen.add(state)
                queue.append((neighbour, next_sign))

    # Build results
    all_reached = set(pos_paths.keys()) | set(neg_paths.keys())
    results: list[PropagationEffect] = []
    for nid in sorted(all_reached):
        p = pos_paths.get(nid, 0)
        n = neg_paths.get(nid, 0)
        if p > 0 and n > 0:
            effect: Literal["+", "-", "ambiguous"] = "ambiguous"
        elif p > 0:
            effect = "+"
        else:
            effect = "-"
        results.append(
            PropagationEffect(
                entity_id=nid,
                effect=effect,
                paths_positive=p,
                paths_negative=n,
            )
        )
    return results


def compute_centrality(
    entities: list[_HasId],
    edges: list[_HasDirection],
) -> list[CentralityResult]:
    """Compute degree and betweenness centrality for all entities.

    Betweenness uses Brandes' algorithm adapted for directed graphs.
    """
    entity_ids = [e.id for e in entities]
    entity_set = set(entity_ids)

    # Degree
    in_deg: dict[str, int] = defaultdict(int)
    out_deg: dict[str, int] = defaultdict(int)
    for e in edges:
        if e.from_id in entity_set:
            out_deg[e.from_id] += 1
        if e.to_id in entity_set:
            in_deg[e.to_id] += 1

    # Betweenness centrality — Brandes' algorithm (directed)
    adj: dict[str, list[str]] = defaultdict(list)
    for e in edges:
        adj[e.from_id].append(e.to_id)

    betweenness: dict[str, float] = {eid: 0.0 for eid in entity_ids}

    for s in entity_ids:
        # BFS from s
        stack: list[str] = []
        predecessors: dict[str, list[str]] = {v: [] for v in entity_ids}
        sigma: dict[str, int] = {v: 0 for v in entity_ids}
        sigma[s] = 1
        dist: dict[str, int] = {v: -1 for v in entity_ids}
        dist[s] = 0
        queue: list[str] = [s]

        while queue:
            v = queue.pop(0)
            stack.append(v)
            for w in adj.get(v, []):
                if w not in entity_set:
                    continue
                if dist[w] < 0:
                    dist[w] = dist[v] + 1
                    queue.append(w)
                if dist[w] == dist[v] + 1:
                    sigma[w] += sigma[v]
                    predecessors[w].append(v)

        # Back-propagation
        delta: dict[str, float] = {v: 0.0 for v in entity_ids}
        while stack:
            w = stack.pop()
            for v in predecessors[w]:
                if sigma[w] > 0:
                    delta[v] += (sigma[v] / sigma[w]) * (1 + delta[w])
            if w != s:
                betweenness[w] += delta[w]

    # Normalise betweenness (for directed graphs: divide by (n-1)(n-2))
    n = len(entity_ids)
    norm = (n - 1) * (n - 2) if n > 2 else 1

    return [
        CentralityResult(
            entity_id=eid,
            degree_in=in_deg.get(eid, 0),
            degree_out=out_deg.get(eid, 0),
            degree_total=in_deg.get(eid, 0) + out_deg.get(eid, 0),
            betweenness=betweenness.get(eid, 0.0) / norm if norm > 0 else 0.0,
        )
        for eid in entity_ids
    ]


def compute_loop_participation(
    entities: list[_HasId],
    loops: list[Loop],
) -> list[LoopParticipation]:
    """Count how many loops each entity participates in."""
    counts: dict[str, int] = defaultdict(int)
    r_counts: dict[str, int] = defaultdict(int)
    b_counts: dict[str, int] = defaultdict(int)

    for loop in loops:
        for nid in loop.node_ids:
            counts[nid] += 1
            if loop.classification == "R":
                r_counts[nid] += 1
            elif loop.classification == "B":
                b_counts[nid] += 1

    return [
        LoopParticipation(
            entity_id=e.id,
            loop_count=counts.get(e.id, 0),
            reinforcing_count=r_counts.get(e.id, 0),
            balancing_count=b_counts.get(e.id, 0),
        )
        for e in entities
    ]


# ═══════════════════════════════════════════════════════════════════════
# DAG ANALYSIS
# ═══════════════════════════════════════════════════════════════════════


def topological_sort(edges: list[_HasDirection]) -> list[str]:
    """Kahn's algorithm for topological ordering.

    Raises ValueError if the graph has cycles.
    Returns a list of node IDs in topological order.
    """
    in_degree: dict[str, int] = defaultdict(int)
    adj: dict[str, list[str]] = defaultdict(list)
    all_node_ids = _all_nodes(edges)

    for nid in all_node_ids:
        in_degree.setdefault(nid, 0)

    for e in edges:
        adj[e.from_id].append(e.to_id)
        in_degree[e.to_id] += 1

    queue = sorted(nid for nid in all_node_ids if in_degree[nid] == 0)
    result: list[str] = []

    while queue:
        node = queue.pop(0)
        result.append(node)
        for neighbour in adj.get(node, []):
            in_degree[neighbour] -= 1
            if in_degree[neighbour] == 0:
                queue.append(neighbour)

    if len(result) != len(all_node_ids):
        raise ValueError("Graph contains a cycle — topological sort is impossible.")
    return result


def d_separation(
    edges: list[_HasDirection],
    x_ids: set[str],
    y_ids: set[str],
    z_ids: set[str],
) -> bool:
    """Test d-separation using the Bayes-Ball algorithm.

    Returns True if X and Y are d-separated given Z.

    Implementation follows Shachter (1998): start from X nodes,
    propagate through the graph following active-path rules, and
    check if any Y node is reached.
    """
    # Build parent and child adjacency
    children: dict[str, list[str]] = defaultdict(list)
    parents: dict[str, list[str]] = defaultdict(list)
    for e in edges:
        children[e.from_id].append(e.to_id)
        parents[e.to_id].append(e.from_id)

    # Ancestors of Z (needed for collider activation)
    z_ancestors: set[str] = set(z_ids)
    queue = list(z_ids)
    while queue:
        node = queue.pop(0)
        for p in parents.get(node, []):
            if p not in z_ancestors:
                z_ancestors.add(p)
                queue.append(p)

    # Bayes-Ball: track (node, direction) pairs
    # direction = "up" means we arrived from a child (going toward parents)
    # direction = "down" means we arrived from a parent (going toward children)
    visited: set[tuple[str, str]] = set()
    reachable: set[str] = set()
    ball_queue: list[tuple[str, str]] = []

    # Start from X nodes — send the ball in both directions
    for x in x_ids:
        ball_queue.append((x, "up"))
        ball_queue.append((x, "down"))

    while ball_queue:
        node, direction = ball_queue.pop(0)
        if (node, direction) in visited:
            continue
        visited.add((node, direction))

        if node not in z_ids:
            reachable.add(node)

        if direction == "up" and node not in z_ids:
            # Arrived from child, node is NOT conditioned on.
            # Non-collider: pass through to parents and to children.
            for p in parents.get(node, []):
                ball_queue.append((p, "up"))
            for c in children.get(node, []):
                ball_queue.append((c, "down"))

        elif direction == "down" and node not in z_ids:
            # Arrived from parent, node is NOT conditioned on.
            # If node is an ancestor of Z (or in Z), collider path
            # can activate — but since node is NOT in Z, only pass
            # downstream (chain behaviour).
            for c in children.get(node, []):
                ball_queue.append((c, "down"))
            # Also: if this node is an ancestor of Z, a collider
            # at this node is activated. We handle this by checking
            # z_ancestors: if the ball arrived "down" and the node
            # is in z_ancestors, pass "up" to parents too.
            if node in z_ancestors:
                for p in parents.get(node, []):
                    ball_queue.append((p, "up"))

        elif direction == "up" and node in z_ids:
            # Arrived from child, node IS conditioned on.
            # Conditioned non-collider blocks downstream but allows
            # passing to parents (explaining away at this node).
            for p in parents.get(node, []):
                ball_queue.append((p, "up"))

        elif direction == "down" and node in z_ids:
            # Arrived from parent, node IS conditioned on.
            # Conditioned non-collider: blocks the chain/fork.
            # But collider activation: pass to parents.
            for p in parents.get(node, []):
                ball_queue.append((p, "up"))

    # X and Y are d-separated if no Y node is reachable
    return not bool(y_ids & reachable)


def markov_blanket(
    entity_id: str,
    edges: list[_HasDirection],
) -> set[str]:
    """Compute the Markov blanket of an entity in a DAG.

    The Markov blanket = parents ∪ children ∪ co-parents
    (other parents of this entity's children).
    """
    parent_ids: set[str] = set()
    child_ids: set[str] = set()

    for e in edges:
        if e.to_id == entity_id:
            parent_ids.add(e.from_id)
        if e.from_id == entity_id:
            child_ids.add(e.to_id)

    # Co-parents: other parents of this entity's children
    co_parent_ids: set[str] = set()
    for e in edges:
        if e.to_id in child_ids and e.from_id != entity_id:
            co_parent_ids.add(e.from_id)

    return parent_ids | child_ids | co_parent_ids


def enumerate_paths(
    from_id: str,
    to_id: str,
    edges: list[_HasDirection],
) -> list[GraphPath]:
    """Find all undirected paths between two nodes.

    Each intermediate node is classified as chain, fork, or collider
    based on edge directions relative to the path.

    Operates on the undirected skeleton of the graph.
    """
    # Build undirected adjacency with edge direction info
    # For each pair, track whether the original edge is from→to or to→from
    undirected: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    # Each entry: (neighbour, edge_id, direction) where direction is
    # "forward" if edge goes current→neighbour, "backward" if neighbour→current
    for e in edges:
        undirected[e.from_id].append((e.to_id, e.id, "forward"))
        undirected[e.to_id].append((e.from_id, e.id, "backward"))

    # DFS to find all simple paths
    raw_paths: list[list[tuple[str, str, str]]] = []
    # Each path element: (node_id, edge_id_used_to_arrive, arrival_direction)

    def _dfs(
        current: str,
        path: list[tuple[str, str, str]],
        visited: set[str],
    ) -> None:
        if current == to_id:
            raw_paths.append(list(path))
            return
        for neighbour, eid, direction in undirected.get(current, []):
            if neighbour not in visited:
                visited.add(neighbour)
                path.append((neighbour, eid, direction))
                _dfs(neighbour, path, visited)
                path.pop()
                visited.discard(neighbour)

    _dfs(from_id, [(from_id, "", "start")], {from_id})

    # Classify nodes on each path
    result: list[GraphPath] = []
    for raw in raw_paths:
        nodes: list[PathNode] = []
        is_directed = True

        for i, (nid, _eid, direction) in enumerate(raw):
            if i == 0 or i == len(raw) - 1:
                nodes.append(PathNode(entity_id=nid, classification="endpoint"))
            else:
                # Classify based on edge directions relative to this node
                # arrival_direction: how we got TO this node
                # departure_direction: how we LEAVE this node
                arrival_dir = raw[i][2]  # direction of edge bringing us here
                departure_dir = raw[i + 1][2]  # direction of edge leaving here

                # "forward" arrival means edge points INTO this node
                # "backward" arrival means edge points AWAY from this node
                # For classification:
                # chain: one in, one out (→ X →)
                # fork: both out (← X →)
                # collider: both in (→ X ←)
                incoming_from_prev = arrival_dir == "forward"
                incoming_from_next = departure_dir == "backward"

                if incoming_from_prev and incoming_from_next:
                    cls = "collider"
                elif not incoming_from_prev and not incoming_from_next:
                    cls = "fork"
                else:
                    cls = "chain"

                nodes.append(PathNode(entity_id=nid, classification=cls))

            # Track if path is fully directed (all edges forward)
            if direction not in ("start", "forward"):
                is_directed = False

        result.append(
            GraphPath(
                nodes=tuple(nodes),
                is_directed=is_directed,
            )
        )

    return result


def adjustment_sets(
    exposure_id: str,
    outcome_id: str,
    edges: list[_HasDirection],
    *,
    max_size: int = 10,
) -> list[set[str]]:
    """Find valid adjustment sets using the backdoor criterion.

    An adjustment set Z is valid if:
    1. No node in Z is a descendant of the exposure.
    2. Z d-separates the exposure from the outcome in the
       *manipulated graph* — the graph with all edges OUT of
       the exposure removed (graph surgery).

    The manipulated graph removes the direct causal effect, so
    d-separation in it tests whether backdoor paths are blocked.

    Returns minimal sufficient adjustment sets. NOTE: the search is only
    implemented for set sizes 1–3 (``max_size`` merely gates which of those
    sizes are tried — sizes 4+ are never enumerated). Returns the empty set
    if no adjustment is needed, or ``[]`` if no valid set ≤3 exists.
    """
    all_node_ids = _all_nodes(edges)
    all_node_ids.discard(exposure_id)
    all_node_ids.discard(outcome_id)

    # Find descendants of exposure (cannot be in adjustment set)
    children_adj: dict[str, list[str]] = defaultdict(list)
    for e in edges:
        children_adj[e.from_id].append(e.to_id)

    desc_of_exposure: set[str] = set()
    queue = list(children_adj.get(exposure_id, []))
    while queue:
        node = queue.pop(0)
        if node not in desc_of_exposure:
            desc_of_exposure.add(node)
            queue.extend(children_adj.get(node, []))

    # Candidate nodes: all non-descendants of exposure
    candidates = sorted(all_node_ids - desc_of_exposure)

    # Build the manipulated graph: remove all edges OUT of exposure
    manipulated_edges = [e for e in edges if e.from_id != exposure_id]

    # Check if empty set is already valid (no backdoor paths)
    if d_separation(manipulated_edges, {exposure_id}, {outcome_id}, set()):
        return [set()]

    # Try increasing set sizes
    valid_sets: list[set[str]] = []

    for c in candidates:
        z = {c}
        if d_separation(manipulated_edges, {exposure_id}, {outcome_id}, z):
            valid_sets.append(z)

    if valid_sets:
        return _minimal_sets(valid_sets)

    if max_size >= 2:
        for i, c1 in enumerate(candidates):
            for c2 in candidates[i + 1 :]:
                z = {c1, c2}
                if d_separation(manipulated_edges, {exposure_id}, {outcome_id}, z):
                    valid_sets.append(z)

    if valid_sets:
        return _minimal_sets(valid_sets)

    if max_size >= 3:
        for i, c1 in enumerate(candidates):
            for j, c2 in enumerate(candidates[i + 1 :], i + 1):
                for c3 in candidates[j + 1 :]:
                    z = {c1, c2, c3}
                    if d_separation(manipulated_edges, {exposure_id}, {outcome_id}, z):
                        valid_sets.append(z)

    return _minimal_sets(valid_sets) if valid_sets else []


def _minimal_sets(sets: list[set[str]]) -> list[set[str]]:
    """Filter to only minimal sets (no proper subset also in the list)."""
    sorted_sets = sorted(sets, key=len)
    minimal: list[set[str]] = []
    for s in sorted_sets:
        if not any(m < s for m in minimal):
            minimal.append(s)
    return minimal
