"""Format causal chains as terminal-friendly text."""

from typing import Any, Dict, List


def format_causal_chains(
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
    top_k: int = 5
) -> List[str]:
    """Build human-readable causal chain strings from graph edges.

    Returns a list of formatted strings suitable for terminal display.
    """
    if not edges:
        return ["(暂无因果链 — 数据不足)"]

    # Build node id → label map
    node_map: Dict[str, str] = {}
    for n in nodes:
        nid = n.get("id", "")
        label = n.get("label", nid)
        node_map[str(nid)] = str(label)

    # Sort edges by weight/confidence descending
    sorted_edges = sorted(
        edges,
        key=lambda e: float(e.get("weight", e.get("value", 0)) or 0),
        reverse=True
    )

    edge_type_labels = {
        "causal": "因果",
        "temporal": "时序",
        "adversarial": "对抗",
    }

    chains = []
    for i, edge in enumerate(sorted_edges[:top_k]):
        from_id = str(edge.get("from", edge.get("source", "?")))
        to_id = str(edge.get("to", edge.get("target", "?")))
        etype = str(edge.get("type", edge.get("label", "causal")))
        weight = float(edge.get("weight", edge.get("value", 0)) or 0)

        from_label = node_map.get(from_id, from_id)
        to_label = node_map.get(to_id, to_id)
        type_cn = edge_type_labels.get(etype, etype)

        chains.append(f"{from_label} → {to_label} ({type_cn}, {weight:.2f})")

    return chains


def format_causal_summary(chains: List[str]) -> str:
    """Render causal chains as a compact terminal block."""
    if not chains:
        return ""

    header = "因果关系链 (关键路径):"
    lines = [header, "-" * len(header)]
    for i, chain in enumerate(chains, 1):
        lines.append(f"  {i}. {chain}")
    return "\n".join(lines)
