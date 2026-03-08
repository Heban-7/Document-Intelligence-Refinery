"""
Structured result of the Query Interface Agent: answer, provenance, and verifiable tool trace.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from src.models.provenance import ProvenanceChain


class ToolCallRecord(BaseModel):
    """Record of one tool invocation for verification and debugging."""
    tool: str = Field(..., description="Tool name: pageindex_navigate, semantic_search, structured_query")
    args: dict = Field(default_factory=dict, description="Arguments passed (e.g. topic, doc_id, n_results)")
    result_summary: str = Field("", description="Human-readable summary, e.g. '3 sections', '5 hits'")
    n_provenance_items: int = Field(0, ge=0, description="Number of provenance items produced by this call")


class QueryResult(BaseModel):
    """Full result of a query: answer text, provenance chain, and tool orchestration trace."""
    answer: str = ""
    provenance: ProvenanceChain = Field(default_factory=ProvenanceChain)
    tool_trace: list[ToolCallRecord] = Field(default_factory=list, description="Ordered list of tool calls executed")
