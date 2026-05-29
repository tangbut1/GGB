"""Standalone HTML graph visualization using pyvis."""

import os
from typing import Any, Dict, List, Optional


def render_graph_html(
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
    keyword: str = "",
    task_id: str = "",
    output_dir: str = "results/reports",
    height: str = "600px",
    width: str = "100%",
) -> str:
    """Generate a standalone interactive graph HTML file using pyvis.

    Returns the output file path.
    """
    try:
        from pyvis.network import Network
    except ImportError:
        return ""

    if not nodes:
        return ""

    os.makedirs(output_dir, exist_ok=True)

    net = Network(
        height=height,
        width=width,
        directed=True,
        bgcolor="#1a1a2e",
        font_color="#e0e0e0",
    )
    net.set_options("""
    {
      "physics": {
        "barnesHut": {
          "gravitationalConstant": -3000,
          "centralGravity": 0.3,
          "springLength": 200,
          "springConstant": 0.04,
          "damping": 0.09
        },
        "maxVelocity": 50,
        "minVelocity": 0.1
      },
      "edges": {
        "smooth": { "type": "continuous" },
        "arrows": { "to": { "enabled": true, "scaleFactor": 0.5 } }
      },
      "nodes": {
        "font": { "size": 14, "face": "sans-serif" }
      },
      "interaction": {
        "hover": true,
        "tooltipDelay": 100,
        "navigationButtons": true
      }
    }
    """)

    # Edge type → color mapping
    edge_colors = {
        "causal": "#e74c3c",       # red
        "temporal": "#3498db",     # blue
        "adversarial": "#e67e22",  # orange
    }
    default_edge_color = "#888888"

    # Add nodes
    for node in nodes:
        nid = node.get("id", "")
        label = node.get("label", str(nid))
        size = max(10, min(50, int(node.get("value", node.get("weight", 10)))))
        title_text = node.get("title", node.get("description", label))
        sentiment = node.get("sentiment", "neutral")
        color_map = {"positive": "#2ecc71", "negative": "#e74c3c", "neutral": "#95a5a6"}
        color = node.get("color", color_map.get(sentiment, "#95a5a6"))

        net.add_node(
            str(nid),
            label=str(label),
            title=str(title_text),
            size=size,
            color=color,
        )

    # Add edges with type-based coloring
    for edge in edges:
        from_id = str(edge.get("from", edge.get("source", "")))
        to_id = str(edge.get("to", edge.get("target", "")))
        if not from_id or not to_id:
            continue

        etype = str(edge.get("type", edge.get("label", "causal")))
        weight = float(edge.get("weight", edge.get("value", 1)) or 1)
        title_text = edge.get("title", edge.get("description", f"{etype} ({weight:.2f})"))
        color = edge_colors.get(etype, default_edge_color)

        net.add_edge(
            from_id, to_id,
            value=weight,
            title=str(title_text),
            color=color,
            arrows="to",
        )

    # Write HTML
    safe_keyword = "".join(c for c in keyword if c.isalnum() or c in "_- ")[:40].strip()
    filename = f"{task_id}_graph.html" if task_id else f"graph_{safe_keyword}.html"
    output_path = os.path.join(output_dir, filename)
    net.save_graph(output_path)

    return os.path.abspath(output_path)
