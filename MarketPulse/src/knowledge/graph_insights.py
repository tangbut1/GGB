"""Graph insights engine — surprising connections, knowledge gaps, community analysis.

Adapted from llm_wiki's multi-signal graph analysis pattern for MarketPulse's
event-based causal graph. Operates on the same node/edge JSON that feeds vis-network.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Dict, List, Set, Tuple


def analyze_graph(nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Main entry point — produce insights from event graph nodes and edges."""
    if not nodes:
        return _empty_result()

    _ensure_ids_int(nodes)
    adj = _build_adjacency(nodes, edges)
    communities = _louvain_communities(nodes, edges)

    return {
        "surprising_connections": _surprising_connections(nodes, edges, adj, communities),
        "knowledge_gaps": _knowledge_gaps(nodes, adj, communities),
        "communities": _community_summary(communities, nodes),
        "graph_stats": _graph_stats(nodes, edges, adj),
    }


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _empty_result() -> Dict[str, Any]:
    return {
        "surprising_connections": [],
        "knowledge_gaps": [],
        "communities": [],
        "graph_stats": {"node_count": 0, "edge_count": 0, "density": 0, "sentiment_distribution": {}},
    }


def _ensure_ids_int(nodes: List[Dict[str, Any]]) -> None:
    for i, node in enumerate(nodes):
        if "id" not in node:
            node["id"] = i + 1


def _build_adjacency(
    nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]]
) -> Dict[int, Set[int]]:
    adj: Dict[int, Set[int]] = defaultdict(set)
    node_ids = {n["id"] for n in nodes}
    for edge in edges:
        src, tgt = edge.get("from"), edge.get("to")
        if src in node_ids and tgt in node_ids:
            adj[src].add(tgt)
            adj[tgt].add(src)
    return adj


def _node_map(nodes: List[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    return {n["id"]: n for n in nodes if isinstance(n.get("id"), int)}


# ---------------------------------------------------------------------------
# Louvain community detection (simplified)
# ---------------------------------------------------------------------------

def _louvain_communities(
    nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]]
) -> Dict[int, int]:
    """Assign each node to a community using greedy modularity optimization."""
    # Initialize: each node in its own community
    n_map = _node_map(nodes)
    all_ids = sorted(n_map.keys())
    communities: Dict[int, int] = {nid: i for i, nid in enumerate(all_ids)}
    adj = _build_adjacency(nodes, edges)
    m = sum(len(v) for v in adj.values()) // 2  # total edges
    if m == 0:
        return communities

    changed = True
    while changed:
        changed = False
        for nid in all_ids:
            neighbors = adj.get(nid, set())
            community_scores: Dict[int, float] = {}
            for neighbor in neighbors:
                c = communities[neighbor]
                if c not in community_scores:
                    # modularity gain for moving node to this community
                    community_scores[c] = _modularity_gain(nid, c, communities, adj, m)
            if not community_scores:
                continue
            best_community = max(community_scores, key=community_scores.get)
            if community_scores[best_community] > 0 and best_community != communities[nid]:
                communities[nid] = best_community
                changed = True

    # Normalize community IDs
    remap = {}
    ordered: Dict[int, int] = {}
    for nid in all_ids:
        cid = communities[nid]
        if cid not in remap:
            remap[cid] = len(remap)
        ordered[nid] = remap[cid]
    return ordered


def _modularity_gain(
    node: int, target_community: int, communities: Dict[int, int],
    adj: Dict[int, Set[int]], m: int,
) -> float:
    """Compute modularity gain of moving `node` to `target_community`."""
    k_i = len(adj.get(node, set()))
    current_c = communities[node]
    neighbors_in_target = sum(1 for n in adj.get(node, set()) if communities.get(n) == target_community)
    neighbors_in_current = sum(1 for n in adj.get(node, set()) if communities.get(n) == current_c)

    gain = neighbors_in_target - neighbors_in_current
    gain -= k_i / (2 * m) * (
        sum(1 for nid, c in communities.items() if c == target_community and nid != node) * k_i
        - sum(1 for nid, c in communities.items() if c == current_c and nid != node) * k_i
    )
    return gain


# ---------------------------------------------------------------------------
# Surprising connections
# ---------------------------------------------------------------------------

def _surprising_connections(
    nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]],
    adj: Dict[int, Set[int]], communities: Dict[int, int],
    limit: int = 6,
) -> List[Dict[str, Any]]:
    n_map = _node_map(nodes)
    total_nodes = len(n_map)
    max_degree = max((len(v) for v in adj.values()), default=1)

    scored: List[Dict[str, Any]] = []
    seen: Set[Tuple[int, int]] = set()

    for edge in edges:
        src_id = edge.get("from")
        tgt_id = edge.get("to")
        if src_id not in n_map or tgt_id not in n_map:
            continue
        key = (min(src_id, tgt_id), max(src_id, tgt_id))
        if key in seen:
            continue
        seen.add(key)

        src, tgt = n_map[src_id], n_map[tgt_id]
        score = 0.0
        reasons: List[str] = []

        # Signal 1: cross-community
        if communities.get(src_id) != communities.get(tgt_id):
            score += 3.0
            reasons.append("跨社区连接")

        # Signal 2: cross-sentiment
        s_type = src.get("sentiment_type")
        t_type = tgt.get("sentiment_type")
        if s_type and t_type and s_type != t_type:
            if {s_type, t_type} in ({"pos", "neg"}, {"neg", "pos"}):
                score += 2.5
                reasons.append("正负情感对立")
            else:
                score += 1.0
                reasons.append("不同情感类型")

        # Signal 3: peripheral-to-hub (proportional to degree gap)
        src_deg = len(adj.get(src_id, set()))
        tgt_deg = len(adj.get(tgt_id, set()))
        hub_threshold = max(3, max_degree * 0.6)
        deg_gap = abs(src_deg - tgt_deg)
        if (src_deg <= 1 and tgt_deg >= hub_threshold) or (tgt_deg <= 1 and src_deg >= hub_threshold):
            # Score proportional to gap: wider gap = more surprising
            gap_score = 1.5 + min(3.0, deg_gap / max(max_degree, 1) * 3.0)
            score += round(gap_score, 1)
            reasons.append(f"孤点↔核心枢纽")
        elif deg_gap >= hub_threshold:
            score += 0.5
            reasons.append("度数差异显著")

        # Signal 4: cross-layer
        s_layer = src.get("layer")
        t_layer = tgt.get("layer")
        if s_layer is not None and t_layer is not None:
            layer_dist = abs(s_layer - t_layer)
            if layer_dist >= 2:
                score += 1.0 + layer_dist * 0.5
                reasons.append("跨因果层级跳连")
            elif layer_dist == 1:
                score += 0.3
                reasons.append("跨层级关联")

        # Signal 5: type distance (distant types = more surprising)
        type_distance_map = {
            ("政策", "舆情"): 2.0, ("政策", "外部事件"): 1.5, ("市场", "舆情"): 1.5,
            ("市场", "外部事件"): 1.0, ("政策", "市场"): 0.8,
        }
        s_type_name = src.get("type", "")
        t_type_name = tgt.get("type", "")
        pair_key = tuple(sorted([s_type_name, t_type_name]))
        type_dist = type_distance_map.get(pair_key, 0)
        if type_dist > 0 and s_type_name != t_type_name:
            score += type_dist
            reasons.append(f"跨类型({s_type_name}↔{t_type_name})")

        # Signal 6: edge weight — lighter edges between important nodes are suspicious
        edge_weight = float(edge.get("weight", 1) or 1)
        if edge_weight <= 1.5 and (src_deg >= 2 or tgt_deg >= 2):
            score += 0.3
        # Bonus: higher-weight edges add granular variation
        score += min(1.0, edge_weight * 0.2)

        # Normalize: divide by square root of total nodes to prevent all scores clumping
        score = round(score, 1)

        if score >= 1.0:
            scored.append({
                "source": {"id": src_id, "label": src.get("label", "")[:25], "type": src.get("type", ""),
                          "sentiment": src.get("sentiment", "")},
                "target": {"id": tgt_id, "label": tgt.get("label", "")[:25], "type": tgt.get("type", ""),
                          "sentiment": tgt.get("sentiment", "")},
                "score": round(score, 1),
                "reasons": reasons,
            })

    scored.sort(key=lambda x: x["score"], reverse=True)
    for i, item in enumerate(scored[:limit]):
        item["id"] = f"sc_{i}"
    return scored[:limit]


# ---------------------------------------------------------------------------
# Knowledge gaps
# ---------------------------------------------------------------------------

def _knowledge_gaps(
    nodes: List[Dict[str, Any]], adj: Dict[int, Set[int]],
    communities: Dict[int, int],
) -> List[Dict[str, Any]]:
    n_map = _node_map(nodes)
    gaps: List[Dict[str, Any]] = []

    community_members: Dict[int, List[int]] = defaultdict(list)
    for nid, cid in communities.items():
        community_members[cid].append(nid)

    # Isolated nodes (degree ≤ 1)
    all_node_ids = set(n_map.keys())
    for nid in all_node_ids:
        deg = len(adj.get(nid, set()))
        if deg <= 1:
            node = n_map.get(nid)
            if not node:
                continue
            gaps.append({
                "type": "isolated",
                "title": f"信息孤岛: {node.get('label', '')[:20]}",
                "description": f"该事件仅与 {deg} 个其他事件关联，可能被低估或缺乏充分报道。",
                "node_id": nid,
                "sentiment": node.get("sentiment", ""),
                "suggestion": "建议对该事件及其背景进行深度搜索（Deep Research）。",
            })

    # Sparse communities (cohesion < 0.15, ≥ 3 members)
    for cid, members in community_members.items():
        if len(members) < 3:
            continue
        internal_edges = 0
        for a in members:
            for b in members:
                if a < b and b in adj.get(a, set()):
                    internal_edges += 1
        possible = len(members) * (len(members) - 1) / 2
        cohesion = internal_edges / possible if possible > 0 else 0
        if cohesion < 0.15:
            labels = [n_map.get(n, {}).get("label", "")[:12] for n in members[:4]]
            gaps.append({
                "type": "sparse_community",
                "title": f"稀疏知识域: {', '.join(labels)}等",
                "description": f"该社区 {len(members)} 个节点内聚度仅 {cohesion:.1%}，交叉引用薄弱。",
                "node_ids": members,
                "cohesion": round(cohesion, 3),
                "suggestion": "建议检查这些事件之间的潜在关联。",
            })

    # Bridge nodes (connect 3+ communities)
    for nid, neighbors in adj.items():
        neighbor_communities = {communities.get(n) for n in neighbors if n in communities}
        if len(neighbor_communities) >= 3:
            node = n_map.get(nid)
            if not node:
                continue
            gaps.append({
                "type": "bridge",
                "title": f"桥接节点: {node.get('label', '')[:20]}",
                "description": f"连接 {len(neighbor_communities)} 个不同知识社区，是跨域关键枢纽。",
                "node_id": nid,
                "bridge_degree": len(neighbor_communities),
                "suggestion": "建议对该节点进行深度搜索，验证其跨域信息整合的可靠性。",
            })

    # Remove duplicates on same node (bridge+isolated can overlap)
    seen_nodes: Set[int] = set()
    deduped: List[Dict[str, Any]] = []
    for g in gaps:
        nid = g.get("node_id")
        if nid is not None:
            if nid in seen_nodes:
                continue
            seen_nodes.add(nid)
        deduped.append(g)

    return deduped[:8]


# ---------------------------------------------------------------------------
# Community summary
# ---------------------------------------------------------------------------

def _community_summary(
    communities: Dict[int, int], nodes: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    n_map = _node_map(nodes)
    members_by_cid: Dict[int, List[int]] = defaultdict(list)
    for nid, cid in communities.items():
        members_by_cid[cid].append(nid)

    summary = []
    for cid, members in sorted(members_by_cid.items(), key=lambda x: -len(x[1])):
        if len(members) < 2:
            continue
        labels = []
        sentiments = []
        types = []
        for nid in members[:6]:
            node = n_map.get(nid, {})
            label = node.get("label", "")
            sentiment = node.get("sentiment", "")
            ntype = node.get("type", "")
            if label:
                labels.append(str(label)[:15])
            if sentiment:
                sentiments.append(sentiment)
            if ntype:
                types.append(ntype)

        dom_sentiment = Counter(sentiments).most_common(1)[0][0] if sentiments else "未知"
        dom_type = Counter(types).most_common(1)[0][0] if types else "未知"

        summary.append({
            "community_id": cid,
            "size": len(members),
            "top_labels": labels,
            "dominant_sentiment": dom_sentiment,
            "dominant_type": dom_type,
            "member_ids": members,
        })

    return summary


# ---------------------------------------------------------------------------
# Graph statistics
# ---------------------------------------------------------------------------

def _graph_stats(
    nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]],
    adj: Dict[int, Set[int]],
) -> Dict[str, Any]:
    n = len(nodes)
    e = len(edges)
    density = (2 * e) / (n * (n - 1)) if n > 1 else 0

    sentiment_counts: Dict[str, int] = {}
    for node in nodes:
        s = node.get("sentiment", node.get("sentiment_type", "未知"))
        sentiment_counts[s] = sentiment_counts.get(s, 0) + 1

    degree_values = [len(v) for v in adj.values()]
    avg_degree = sum(degree_values) / len(degree_values) if degree_values else 0
    max_deg = max(degree_values) if degree_values else 0

    return {
        "node_count": n,
        "edge_count": e,
        "density": round(density, 4),
        "avg_degree": round(avg_degree, 1),
        "max_degree": max_deg,
        "sentiment_distribution": sentiment_counts,
    }
