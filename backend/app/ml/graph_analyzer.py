"""Graph-based transaction network analysis for layering detection.

Uses NetworkX to build a transaction graph and detect:
- Multi-hop money laundering chains (A→B→C→D→A)
- Fan-out/fan-in patterns (one account distributing to many)
- Community structures (clusters of suspicious accounts)
- High-centrality nodes (money mules)

Features computed here can be fed as additional inputs to the ML models.
"""

import logging
from collections import defaultdict

import numpy as np

logger = logging.getLogger(__name__)

try:
    import networkx as nx

    HAS_NETWORKX = True
except ImportError:
    HAS_NETWORKX = False
    logger.info("NetworkX not installed — graph analysis disabled")


class TransactionGraphAnalyzer:
    """Builds and analyzes a transaction graph for AML pattern detection."""

    def __init__(self):
        if not HAS_NETWORKX:
            self.graph = None
            return
        self.graph = nx.DiGraph()
        self._edge_amounts: dict[tuple[str, str], list[float]] = defaultdict(list)

    @property
    def is_available(self) -> bool:
        return HAS_NETWORKX and self.graph is not None

    def build_graph(self, transactions: list) -> None:
        """Build a directed graph from transfer transactions.

        Nodes = account IDs, edges = transfers weighted by total amount.
        """
        if not self.is_available:
            return

        self.graph.clear()
        self._edge_amounts.clear()

        for tx in transactions:
            if (
                hasattr(tx, "transaction_type")
                and tx.transaction_type.value == "transfer"
                and tx.counterparty_account_id
            ):
                src = tx.fineract_account_id
                dst = tx.counterparty_account_id
                self._edge_amounts[(src, dst)].append(tx.amount)

        # Add edges with aggregate weights
        for (src, dst), amounts in self._edge_amounts.items():
            self.graph.add_edge(
                src,
                dst,
                weight=sum(amounts),
                count=len(amounts),
                avg_amount=np.mean(amounts),
            )

    def detect_cycles(self, max_length: int = 5) -> list[list[str]]:
        """Find all cycles up to max_length (potential layering patterns).

        Returns:
            List of cycles, each a list of account IDs.
        """
        if not self.is_available or len(self.graph) == 0:
            return []

        cycles = []
        try:
            for cycle in nx.simple_cycles(self.graph, length_bound=max_length):
                if len(cycle) >= 3:  # Skip trivial A→B→A (already caught by rules)
                    cycles.append(cycle)
        except Exception as e:
            logger.warning("Cycle detection failed: %s", e)
        return cycles

    def detect_fan_out(self, threshold: int = 5) -> list[dict]:
        """Find accounts that send to many different recipients.

        Args:
            threshold: Minimum number of unique recipients to flag.

        Returns:
            List of dicts: {account, recipient_count, total_amount}
        """
        if not self.is_available:
            return []

        results = []
        for node in self.graph.nodes():
            out_degree = self.graph.out_degree(node)
            if out_degree >= threshold:
                total = sum(
                    self.graph[node][succ]["weight"]
                    for succ in self.graph.successors(node)
                )
                results.append({
                    "account": node,
                    "recipient_count": out_degree,
                    "total_amount": total,
                })
        return sorted(results, key=lambda x: x["recipient_count"], reverse=True)

    def detect_fan_in(self, threshold: int = 5) -> list[dict]:
        """Find accounts that receive from many different senders.

        Args:
            threshold: Minimum number of unique senders to flag.

        Returns:
            List of dicts: {account, sender_count, total_amount}
        """
        if not self.is_available:
            return []

        results = []
        for node in self.graph.nodes():
            in_degree = self.graph.in_degree(node)
            if in_degree >= threshold:
                total = sum(
                    self.graph[pred][node]["weight"]
                    for pred in self.graph.predecessors(node)
                )
                results.append({
                    "account": node,
                    "sender_count": in_degree,
                    "total_amount": total,
                })
        return sorted(results, key=lambda x: x["sender_count"], reverse=True)

    def get_network_features(self, account_id: str) -> dict[str, float]:
        """Compute graph-based features for a specific account.

        These features can be added to the ML feature vector to improve
        fraud detection with network-level signals.

        Returns:
            Dict of feature_name -> value.
        """
        if not self.is_available or account_id not in self.graph:
            return {
                "out_degree": 0.0,
                "in_degree": 0.0,
                "total_sent": 0.0,
                "total_received": 0.0,
                "pagerank": 0.0,
                "is_in_cycle": 0.0,
            }

        out_degree = float(self.graph.out_degree(account_id))
        in_degree = float(self.graph.in_degree(account_id))

        total_sent = sum(
            self.graph[account_id][succ]["weight"]
            for succ in self.graph.successors(account_id)
        )
        total_received = sum(
            self.graph[pred][account_id]["weight"]
            for pred in self.graph.predecessors(account_id)
        )

        # PageRank — identifies important nodes in the money flow network
        try:
            pagerank = nx.pagerank(self.graph, alpha=0.85).get(account_id, 0.0)
        except Exception:
            pagerank = 0.0

        # Check if account participates in any cycle
        is_in_cycle = 0.0
        try:
            for cycle in nx.simple_cycles(self.graph, length_bound=5):
                if account_id in cycle:
                    is_in_cycle = 1.0
                    break
        except Exception:
            pass

        return {
            "out_degree": out_degree,
            "in_degree": in_degree,
            "total_sent": total_sent,
            "total_received": total_received,
            "pagerank": pagerank,
            "is_in_cycle": is_in_cycle,
        }

    def get_summary(self) -> dict:
        """Get summary statistics of the transaction graph."""
        if not self.is_available:
            return {"available": False}

        return {
            "available": True,
            "nodes": self.graph.number_of_nodes(),
            "edges": self.graph.number_of_edges(),
            "density": nx.density(self.graph) if self.graph.number_of_nodes() > 1 else 0.0,
            "connected_components": nx.number_weakly_connected_components(self.graph),
        }
