"""Structural checks shared by contracts and the development adapter."""

from itertools import combinations

import networkx as nx

from causalbridge.schemas import Query, RuntimeCase


def _known_node(case: RuntimeCase, node: str) -> nx.DiGraph:
    graph = case.graph()
    if node not in graph:
        raise ValueError(f"Unknown graph node: {node}")
    return graph


def parents(case: RuntimeCase, node: str) -> tuple[str, ...]:
    """Direct causes of a node, in deterministic order."""
    return tuple(sorted(_known_node(case, node).predecessors(node)))


def ancestors(case: RuntimeCase, node: str) -> tuple[str, ...]:
    """All upstream nodes, in deterministic order."""
    return tuple(sorted(nx.ancestors(_known_node(case, node), node)))


def descendants(case: RuntimeCase, node: str) -> tuple[str, ...]:
    """All downstream nodes, in deterministic order."""
    return tuple(sorted(nx.descendants(_known_node(case, node), node)))


def valid_adjustment_sets(case: RuntimeCase, query: Query) -> tuple[tuple[str, ...], ...]:
    """Enumerate standard backdoor sets, ordered by size and then node ID."""
    query.bind(case)
    candidates = sorted(set(case.graph_nodes) - {query.cause, query.outcome})
    valid = []
    for size in range(len(candidates) + 1):
        for selected in combinations(candidates, size):
            if valid_adjustment(case, query.model_copy(update={"adjustment_set": selected})):
                valid.append(selected)
    return tuple(valid)


def has_path(case: RuntimeCase, query: Query) -> bool:
    query.bind(case)
    return nx.has_path(case.graph(), query.cause, query.outcome)


def valid_adjustment(case: RuntimeCase, query: Query) -> bool:
    """Pearl's backdoor criterion, a sufficient (not exhaustive) adjustment rule."""
    query.bind(case)
    graph = case.graph()
    adjustment = set(query.adjustment_set)
    if adjustment & nx.descendants(graph, query.cause):
        return False
    graph.remove_edges_from(list(graph.out_edges(query.cause)))
    return nx.is_d_separator(graph, {query.cause}, {query.outcome}, adjustment)
