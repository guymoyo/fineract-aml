"""Graph visualization schemas — nodes and edges for D3/Cytoscape rendering."""

from pydantic import BaseModel


class GraphNode(BaseModel):
    id: str
    label: str
    node_type: str          # "account" | "agent" | "merchant" | "external"
    risk_score: float | None = None
    transaction_count: int = 0
    total_volume: float = 0.0
    is_flagged: bool = False


class GraphEdge(BaseModel):
    source: str
    target: str
    weight: float           # Total transferred amount
    tx_count: int = 0
    edge_type: str = "transfer"  # "transfer" | "deposit" | "withdrawal"


class GraphResponse(BaseModel):
    account_id: str
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    depth: int = 2
    node_count: int = 0
    edge_count: int = 0
