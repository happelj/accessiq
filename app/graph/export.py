from __future__ import annotations

from .models import AuthorizationGraph


def export_json(graph: AuthorizationGraph) -> dict[str, object]:
    return graph.export()


def export_mermaid(graph: AuthorizationGraph) -> str:
    lines = ["flowchart LR"]
    for node in sorted(graph.nodes.values(), key=lambda item: item.id):
        lines.append(f'    {safe_id(node.id)}["{_escape(node.label)}"]')
    for edge in graph.edges:
        lines.append(
            f"    {safe_id(edge.source)} -->|{edge.type.value}| {safe_id(edge.target)}"
        )
    return "\n".join(lines)


def export_graphviz_dot(graph: AuthorizationGraph) -> str:
    lines = ["digraph AuthorizationGraph {"]
    for node in sorted(graph.nodes.values(), key=lambda item: item.id):
        lines.append(f'  "{node.id}" [label="{_escape(node.label)}"];')
    for edge in graph.edges:
        lines.append(
            f'  "{edge.source}" -> "{edge.target}" [label="{edge.type.value}"];'
        )
    lines.append("}")
    return "\n".join(lines)


def safe_id(value: str) -> str:
    return (
        value.replace(":", "_")
        .replace("-", "_")
        .replace(".", "_")
        .replace("/", "_")
    )


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
