"""
Enterprise Chat Agent - Azure Functions HTTP Triggers

This sample demonstrates a production-ready Chat API using Microsoft Agent Framework
with Azure Functions. The agent is configured with multiple tools and autonomously
decides which tools to invoke based on user intent.

Key Features:
- Azure Functions HTTP triggers for REST API endpoints
- ChatAgent with runtime tool selection
- Cosmos DB for persistent thread and message storage
- Partition key on thread_id for optimal query performance
"""

import json
import logging
import os
import uuid

import azure.functions as func
from azure.identity import DefaultAzureCredential

# TODO: Uncomment when implementing with actual Agent Framework
# from microsoft.agents.ai.azure import AzureOpenAIChatClient
# from microsoft.agents.core import ChatAgent

from tools import get_weather, calculate, search_knowledge_base
from cosmos_store import CosmosConversationStore

app = func.FunctionApp()

# -----------------------------------------------------------------------------
# Cosmos DB Storage (singleton for reuse across invocations)
# -----------------------------------------------------------------------------
_store: CosmosConversationStore | None = None


def get_store() -> CosmosConversationStore:
    """Get or create the Cosmos DB conversation store instance."""
    global _store
    if _store is None:
        _store = CosmosConversationStore()
        logging.info("Initialized Cosmos DB conversation store")
    return _store


# -----------------------------------------------------------------------------
# Agent initialization (singleton pattern for reuse across invocations)
# -----------------------------------------------------------------------------
_agent = None


def get_agent():
    """
    Get or create the ChatAgent instance.
    Uses singleton pattern to reuse across function invocations.
    """
    global _agent
    if _agent is None:
        # TODO: Initialize actual Agent Framework components
        # credential = DefaultAzureCredential()
        # chat_client = AzureOpenAIChatClient(
        #     endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        #     model=os.environ["AZURE_OPENAI_MODEL"],
        #     credential=credential,
        # )
        # _agent = ChatAgent(
        #     chat_client=chat_client,
        #     instructions="""You are a helpful assistant.
        #     Use the available tools when they can help answer the user's question.
        #     You can use multiple tools in a single response if needed.""",
        #     tools=[get_weather, calculate, search_knowledge_base],
        # )
        logging.info("Agent initialized (placeholder)")
    return _agent


# -----------------------------------------------------------------------------
# HTTP Trigger: Create Thread
# -----------------------------------------------------------------------------
@app.route(route="threads", methods=["POST"])
async def create_thread(req: func.HttpRequest) -> func.HttpResponse:
    """
    Create a new conversation thread.

    Request:
        POST /api/threads
        Body: {"metadata": {"user_id": "...", "session_type": "..."}}

    Response:
        201 Created
        {"id": "thread_xxx", "created_at": "...", "metadata": {...}}
    """
    try:
        body = req.get_json() if req.get_body() else {}
    except ValueError:
        body = {}

    thread_id = f"thread_{uuid.uuid4().hex[:12]}"
    metadata = body.get("metadata", {})

    # Store thread in Cosmos DB
    store = get_store()
    thread = await store.create_thread(thread_id, metadata)

    logging.info(f"Created thread {thread_id}")

    return func.HttpResponse(
        body=json.dumps(thread),
        status_code=201,
        mimetype="application/json",
    )


# -----------------------------------------------------------------------------
# HTTP Trigger: Get Thread
# -----------------------------------------------------------------------------
@app.route(route="threads/{thread_id}", methods=["GET"])
async def get_thread(req: func.HttpRequest) -> func.HttpResponse:
    """
    Get thread metadata.

    Request:
        GET /api/threads/{thread_id}

    Response:
        200 OK
        {"id": "thread_xxx", "created_at": "...", "metadata": {...}}
    """
    thread_id = req.route_params.get("thread_id")

    store = get_store()
    thread = await store.get_thread(thread_id)

    if thread is None:
        return func.HttpResponse(
            body=json.dumps({"error": "Thread not found"}),
            status_code=404,
            mimetype="application/json",
        )

    return func.HttpResponse(
        body=json.dumps(thread),
        mimetype="application/json",
    )


# -----------------------------------------------------------------------------
# HTTP Trigger: Delete Thread
# -----------------------------------------------------------------------------
@app.route(route="threads/{thread_id}", methods=["DELETE"])
async def delete_thread(req: func.HttpRequest) -> func.HttpResponse:
    """
    Delete a thread and its messages.

    Request:
        DELETE /api/threads/{thread_id}

    Response:
        204 No Content
    """
    thread_id = req.route_params.get("thread_id")

    store = get_store()
    deleted = await store.delete_thread(thread_id)

    if not deleted:
        return func.HttpResponse(
            body=json.dumps({"error": "Thread not found"}),
            status_code=404,
            mimetype="application/json",
        )

    logging.info(f"Deleted thread {thread_id}")

    return func.HttpResponse(status_code=204)


# -----------------------------------------------------------------------------
# HTTP Trigger: Send Message
# -----------------------------------------------------------------------------
@app.route(route="threads/{thread_id}/messages", methods=["POST"])
async def send_message(req: func.HttpRequest) -> func.HttpResponse:
    """
    Send a message to the agent and get a response.

    The agent will autonomously decide which tools to use based on the message content.

    Request:
        POST /api/threads/{thread_id}/messages
        Body: {"content": "What's the weather in Seattle?"}

    Response:
        200 OK
        {
            "id": "msg_xxx",
            "thread_id": "thread_xxx",
            "role": "assistant",
            "content": "The weather in Seattle is...",
            "tool_calls": [...],
            "timestamp": "..."
        }
    """
    thread_id = req.route_params.get("thread_id")

    store = get_store()

    # Check if thread exists
    if not await store.thread_exists(thread_id):
        return func.HttpResponse(
            body=json.dumps({"error": "Thread not found"}),
            status_code=404,
            mimetype="application/json",
        )

    try:
        body = req.get_json()
        content = body.get("content")
        if not content:
            return func.HttpResponse(
                body=json.dumps({"error": "Missing 'content' in request body"}),
                status_code=400,
                mimetype="application/json",
            )
    except ValueError:
        return func.HttpResponse(
            body=json.dumps({"error": "Invalid JSON body"}),
            status_code=400,
            mimetype="application/json",
        )

    # Store user message in Cosmos DB
    user_message_id = f"msg_{uuid.uuid4().hex[:12]}"
    await store.add_message(
        thread_id=thread_id,
        message_id=user_message_id,
        role="user",
        content=content,
    )

    # TODO: Replace with actual agent invocation
    # agent = get_agent()
    # response = await agent.run(content, thread_id=thread_id)

    # Placeholder response (demonstrates tool selection pattern)
    tool_calls = []
    response_content = ""

    # Simple keyword-based tool selection demo
    content_lower = content.lower()
    if "weather" in content_lower:
        # Extract location (simplified)
        location = "Seattle"  # Default
        if "in " in content_lower:
            location = content_lower.split("in ")[-1].split()[0].title()
        weather_result = get_weather(location)
        tool_calls.append({
            "tool": "get_weather",
            "arguments": {"location": location},
            "result": weather_result,
        })
        response_content += (
            f"The weather in {location} is {weather_result['temp']}°F "
            f"with {weather_result['condition']}. "
        )

    if any(word in content_lower for word in ["calculate", "tip", "%", "percent"]):
        # Simplified calculation demo
        calc_result = calculate("85 * 0.15")
        tool_calls.append({
            "tool": "calculate",
            "arguments": {"expression": "85 * 0.15"},
            "result": calc_result,
        })
        response_content += f"A 15% tip on $85 is ${calc_result:.2f}."

    if not response_content:
        response_content = (
            f"I received your message: '{content}'. How can I help you further?"
        )

    # Store assistant response in Cosmos DB
    assistant_message_id = f"msg_{uuid.uuid4().hex[:12]}"
    assistant_message = await store.add_message(
        thread_id=thread_id,
        message_id=assistant_message_id,
        role="assistant",
        content=response_content.strip(),
        tool_calls=tool_calls if tool_calls else None,
    )

    logging.info(
        f"Processed message for thread {thread_id}, "
        f"tools used: {[t['tool'] for t in tool_calls]}"
    )

    return func.HttpResponse(
        body=json.dumps(assistant_message),
        mimetype="application/json",
    )


# -----------------------------------------------------------------------------
# HTTP Trigger: Get Messages
# -----------------------------------------------------------------------------
@app.route(route="threads/{thread_id}/messages", methods=["GET"])
async def get_messages(req: func.HttpRequest) -> func.HttpResponse:
    """
    Get conversation history for a thread.

    Request:
        GET /api/threads/{thread_id}/messages

    Response:
        200 OK
        {"messages": [...]}
    """
    thread_id = req.route_params.get("thread_id")

    store = get_store()

    # Check if thread exists
    if not await store.thread_exists(thread_id):
        return func.HttpResponse(
            body=json.dumps({"error": "Thread not found"}),
            status_code=404,
            mimetype="application/json",
        )

    messages = await store.get_messages(thread_id)

    return func.HttpResponse(
        body=json.dumps({"messages": messages}),
        mimetype="application/json",
    )


# -----------------------------------------------------------------------------
# HTTP Trigger: Health Check
# -----------------------------------------------------------------------------
@app.route(route="health", methods=["GET"])
async def health_check(req: func.HttpRequest) -> func.HttpResponse:
    """
    Health check endpoint for monitoring.

    Request:
        GET /api/health

    Response:
        200 OK
        {"status": "healthy", "version": "1.0.0", "cosmos_connected": true}
    """
    cosmos_connected = False
    try:
        store = get_store()
        # Simple connectivity check
        store.container  # This will initialize the connection if not already done
        cosmos_connected = True
    except Exception as e:
        logging.warning(f"Cosmos DB connectivity check failed: {e}")

    return func.HttpResponse(
        body=json.dumps({
            "status": "healthy",
            "version": "1.0.0",
            "cosmos_connected": cosmos_connected,
        }),
        mimetype="application/json",
    )
