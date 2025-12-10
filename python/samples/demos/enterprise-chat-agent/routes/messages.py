# Copyright (c) Microsoft. All rights reserved.

"""Message endpoints for thread conversations."""

import json
import logging
import uuid

import azure.functions as func

from services import http_request_span, cosmos_span
from routes.threads import get_store
from tools import get_weather, calculate, search_knowledge_base

bp = func.Blueprint()


@bp.route(route="threads/{thread_id}/messages", methods=["POST"])
async def send_message(req: func.HttpRequest) -> func.HttpResponse:
    """
    Send a message to the agent and get a response.

    The agent will autonomously decide which tools to use based on
    the message content.

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

    async with http_request_span(
        "POST", "/threads/{thread_id}/messages", thread_id=thread_id
    ) as span:
        store = get_store()

        # Check if thread exists
        async with cosmos_span("read", "threads", thread_id):
            thread_exists = await store.thread_exists(thread_id)

        if not thread_exists:
            span.set_attribute("http.status_code", 404)
            return func.HttpResponse(
                body=json.dumps({"error": "Thread not found"}),
                status_code=404,
                mimetype="application/json",
            )

        try:
            body = req.get_json()
            content = body.get("content")
            if not content:
                span.set_attribute("http.status_code", 400)
                return func.HttpResponse(
                    body=json.dumps(
                        {"error": "Missing 'content' in request body"}
                    ),
                    status_code=400,
                    mimetype="application/json",
                )
        except ValueError:
            span.set_attribute("http.status_code", 400)
            return func.HttpResponse(
                body=json.dumps({"error": "Invalid JSON body"}),
                status_code=400,
                mimetype="application/json",
            )

        # Store user message in Cosmos DB
        user_message_id = f"msg_{uuid.uuid4().hex[:12]}"
        async with cosmos_span("upsert", "messages", thread_id):
            await store.add_message(
                thread_id=thread_id,
                message_id=user_message_id,
                role="user",
                content=content,
                metadata={"client": "http_api"},
            )

        # TODO: Replace with actual agent invocation
        # agent = get_agent()
        # response = await agent.run(content, thread_id=thread_id)
        # Framework auto-creates: invoke_agent, chat, execute_tool spans

        # Placeholder response (demonstrates tool selection pattern)
        tool_calls = []
        response_content = ""

        # Simple keyword-based tool selection demo
        content_lower = content.lower()
        if "weather" in content_lower:
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

        calc_keywords = ["calculate", "tip", "%", "percent"]
        if any(word in content_lower for word in calc_keywords):
            calc_result = calculate("85 * 0.15")
            tool_calls.append({
                "tool": "calculate",
                "arguments": {"expression": "85 * 0.15"},
                "result": calc_result,
            })
            response_content += f"A 15% tip on $85 is ${calc_result:.2f}."

        if not response_content:
            response_content = (
                f"I received your message: '{content}'. "
                "How can I help you further?"
            )

        # Store assistant response in Cosmos DB
        assistant_message_id = f"msg_{uuid.uuid4().hex[:12]}"

        # Example: Add sources for RAG
        sources = None
        if "weather" in content_lower:
            sources = [
                {
                    "title": "Weather Service API",
                    "url": "https://api.weather.example.com",
                    "snippet": "Real-time weather data",
                }
            ]

        async with cosmos_span("upsert", "messages", thread_id):
            assistant_message = await store.add_message(
                thread_id=thread_id,
                message_id=assistant_message_id,
                role="assistant",
                content=response_content.strip(),
                tool_calls=tool_calls if tool_calls else None,
                sources=sources,
                metadata={"model": "placeholder"},
            )

        logging.info(
            f"Processed message for thread {thread_id}, "
            f"tools used: {[t['tool'] for t in tool_calls]}"
        )

        span.set_attribute("http.status_code", 200)
        return func.HttpResponse(
            body=json.dumps(assistant_message),
            mimetype="application/json",
        )


@bp.route(route="threads/{thread_id}/messages", methods=["GET"])
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

    async with http_request_span(
        "GET", "/threads/{thread_id}/messages", thread_id=thread_id
    ) as span:
        store = get_store()

        # Check if thread exists
        async with cosmos_span("read", "threads", thread_id):
            thread_exists = await store.thread_exists(thread_id)

        if not thread_exists:
            span.set_attribute("http.status_code", 404)
            return func.HttpResponse(
                body=json.dumps({"error": "Thread not found"}),
                status_code=404,
                mimetype="application/json",
            )

        async with cosmos_span("query", "messages", thread_id):
            messages = await store.get_messages(thread_id)

        span.set_attribute("http.status_code", 200)
        return func.HttpResponse(
            body=json.dumps({"messages": messages}),
            mimetype="application/json",
        )
