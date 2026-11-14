"""Reproducible small binary DAGs and CPTs for Track A benchmark producers."""

from itertools import product
from random import Random

import networkx as nx

from causalbridge.schemas import CPT

MAX_NODES = 8
MIN_PROBABILITY = 0.1
MAX_PROBABILITY = 0.9


def _integer(name: str, value: int) -> None:
    if type(value) is not int:
        raise ValueError(f"{name} must be an integer")


def generate_dag(node_count: int, edge_count: int, max_in_degree: int, *, seed: int) -> nx.DiGraph:
    """Generate a DAG with exactly the requested nodes and edges, including isolates.

    Nodes are named N0, N1, ... . A seeded random topological order makes every
    selected edge point forward, so adding edges cannot create a cycle.
    """
    for name, value in (
        ("node_count", node_count),
        ("edge_count", edge_count),
        ("max_in_degree", max_in_degree),
        ("seed", seed),
    ):
        _integer(name, value)
    if not 2 <= node_count <= MAX_NODES:
        raise ValueError(f"node_count must be between 2 and {MAX_NODES}")
    if not 0 <= max_in_degree < node_count:
        raise ValueError("max_in_degree must be between 0 and node_count - 1")
    capacity = sum(min(max_in_degree, position) for position in range(node_count))
    if not 0 <= edge_count <= capacity:
        raise ValueError(f"edge_count must be between 0 and {capacity}")

    rng = Random(seed)
    order = [f"N{i}" for i in range(node_count)]
    rng.shuffle(order)
    candidates = [
        (source, target) for position, target in enumerate(order) for source in order[:position]
    ]
    rng.shuffle(candidates)
    graph = nx.DiGraph()
    graph.add_nodes_from(f"N{i}" for i in range(node_count))
    for source, target in candidates:
        if graph.number_of_edges() == edge_count:
            break
        if graph.in_degree(target) < max_in_degree:
            graph.add_edge(source, target)
    if graph.number_of_edges() != edge_count or not nx.is_directed_acyclic_graph(graph):
        raise RuntimeError("DAG generation failed to satisfy its constraints")
    return graph


def generate_cpts(graph: nx.DiGraph, *, seed: int) -> tuple[CPT, ...]:
    """Generate complete binary CPTs, using sorted parent IDs for each table."""
    _integer("seed", seed)
    if type(graph) is not nx.DiGraph:
        raise ValueError("graph must be a NetworkX DiGraph")
    nodes = list(graph.nodes)
    if not 2 <= len(nodes) <= MAX_NODES:
        raise ValueError(f"graph must have between 2 and {MAX_NODES} nodes")
    if any(type(node) is not str or not node.strip() for node in nodes):
        raise ValueError("graph nodes must be nonempty strings")
    if not nx.is_directed_acyclic_graph(graph):
        raise ValueError("graph must be a DAG")

    rng = Random(seed)
    tables = []
    for node in sorted(nodes):
        parents = tuple(sorted(graph.predecessors(node)))
        rows = {
            "".join(bits): rng.uniform(MIN_PROBABILITY, MAX_PROBABILITY)
            for bits in product("01", repeat=len(parents))
        }
        tables.append(CPT(node=node, parents=parents, p_one=rows))
    return tuple(tables)
