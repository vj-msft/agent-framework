# Copyright (c) Microsoft. All rights reserved.

"""
Core modules for Enterprise Chat Agent.

This package contains foundational components:
- cosmos_store: Azure Cosmos DB storage for threads and messages
- observability: OpenTelemetry instrumentation for tracing
"""

from services.cosmos_store import CosmosConversationStore
from services.observability import (
    init_observability,
    http_request_span,
    cosmos_span,
    validation_span,
    EnterpriseAgentAttr,
)

__all__ = [
    "CosmosConversationStore",
    "init_observability",
    "http_request_span",
    "cosmos_span",
    "validation_span",
    "EnterpriseAgentAttr",
]
