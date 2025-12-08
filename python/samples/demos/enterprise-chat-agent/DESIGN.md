---
status: proposed
contact: @vj-msft
date: 2024-12-06
deciders: TBD
consulted: TBD
informed: TBD
---

# Production Chat API with Azure Functions, Cosmos DB & Agent Framework

## References

- **GitHub Issue**: [#2436 - Python: [Sample Request] Production Chat API with Azure Functions, Cosmos DB & Agent Framework](https://github.com/microsoft/agent-framework/issues/2436)
- **Microsoft Documentation**:
  - [Create and run a durable agent (Python)](https://learn.microsoft.com/en-us/agent-framework/tutorials/agents/create-and-run-durable-agent)
  - [Agent Framework Tools](https://learn.microsoft.com/en-us/agent-framework/concepts/tools)
  - [Multi-agent Reference Architecture](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/architecture/build-multi-agent-framework-solution)
  - [Well-Architected AI Agents](https://learn.microsoft.com/en-us/azure/well-architected/service-guides/ai-agent-architecture)

## What is the goal of this feature?

Provide a **production-ready sample** demonstrating how to build a scalable Chat API using the Microsoft Agent Framework with:

1. **Azure Functions** for serverless, scalable hosting
2. **Azure Cosmos DB** for durable conversation persistence
3. **Function Tools** showcasing runtime tool selection by the agent

### Value Proposition

- Developers can use this sample as a reference architecture for deploying Agent Framework in production
- Demonstrates enterprise patterns: state persistence, observability, and thread-based conversations
- Shows the power of **agent autonomy** - the agent decides which tools to invoke at runtime based on conversation context

### Success Metrics

1. Sample is referenced in at least 3 external blog posts/tutorials within 6 months
2. Sample serves as the canonical reference for "Agent Framework + Azure Functions + Cosmos DB" stack

## What is the problem being solved?

### Current Pain Points

1. **No production-ready Python sample exists** - Existing samples focus on getting started scenarios, not production deployment
2. **Gap in persistence guidance** - .NET has `CosmosNoSql` package, Python has no equivalent sample or implementation
3. **Tool selection patterns unclear** - Developers need to see how agents autonomously select tools at runtime

### Why is this hard today?

- Developers must piece together patterns from multiple sources
- No reference implementation for Cosmos DB persistence in Python
- Azure Functions + Agent Framework integration patterns are spread across docs

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           Client Applications                            │
│                    (Web, Mobile, CLI, Postman, etc.)                    │
└─────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        Azure Functions (Flex Consumption)                │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                     HTTP Trigger Endpoints                       │   │
│  │  POST /api/chat/{thread_id}     - Send message                  │   │
│  │  GET  /api/chat/{thread_id}     - Get thread history            │   │
│  │  POST /api/threads              - Create new thread             │   │
│  │  DELETE /api/threads/{id}       - Delete thread                 │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                     │                                    │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                        ChatAgent                                 │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │   │
│  │  │ WeatherTool │  │ SearchTool  │  │ CalculatorTool │           │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘              │   │
│  │                                                                  │   │
│  │  Agent autonomously selects tools based on user intent          │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                                     │
                    ┌────────────────┼────────────────┐
                    ▼                ▼                ▼
         ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
         │ Azure OpenAI │  │  Cosmos DB   │  │   App        │
         │   (GPT-4o)   │  │  (NoSQL)     │  │  Insights    │
         │              │  │              │  │              │
         │ Chat model   │  │ Threads &    │  │ Telemetry    │
         │ completions  │  │ Messages     │  │ & Tracing    │
         └──────────────┘  └──────────────┘  └──────────────┘
```

## Key Design Decisions

### 1. Runtime Tool Selection (Agent Autonomy)

The agent is configured with multiple tools but **decides at runtime** which tool(s) to invoke:

```python
# Tools are registered, but agent decides when to use them
agent = ChatAgent(
    chat_client=azure_openai_client,
    instructions="You are a helpful assistant. Use available tools when needed.",
    tools=[
        get_weather,      # Weather information
        search_web,       # Web search
        calculate,        # Math operations
        get_stock_price,  # Stock quotes
    ]
)

# User asks: "What's the weather in Seattle and what's 15% tip on $85?"
# Agent autonomously invokes: get_weather("Seattle") AND calculate("85 * 0.15")
```

### 2. Cosmos DB Persistence Strategy

**Data Model**: One document per message (optimized for append-heavy workloads)

```json
{
  "id": "msg_abc123",
  "thread_id": "thread_xyz789",
  "role": "user",
  "content": "What's the weather in Seattle?",
  "timestamp": "2024-12-06T10:30:00Z",
  "metadata": {
    "tool_calls": null,
    "model": null
  }
}
```

**Partition Strategy**:

- **Partition Key**: `/thread_id` (optimal for retrieving all messages in a conversation)
- All messages for a thread are stored together, enabling efficient queries

### 3. Azure Functions Hosting

Using **HTTP Triggers** for a familiar REST API pattern:

- Standard HTTP trigger endpoints (POST, GET, DELETE)
- Explicit state management via Cosmos DB
- Flex Consumption plan for serverless scaling (0 to thousands of instances)
- Simple deployment model using Azure Functions Core Tools or `azd`

### 4. Simple Thread-Based Architecture

```python
# Thread isolation via partition key
async def get_thread_messages(thread_id: str):
    query = "SELECT * FROM c WHERE c.thread_id = @thread_id ORDER BY c.timestamp"
    return await container.query_items(
        query=query,
        parameters=[{"name": "@thread_id", "value": thread_id}],
        partition_key=thread_id  # Scoped to thread's partition
    )
```

## API Design

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/threads` | Create a new conversation thread |
| `GET` | `/api/threads/{thread_id}` | Get thread metadata |
| `DELETE` | `/api/threads/{thread_id}` | Delete a thread and its messages |
| `POST` | `/api/threads/{thread_id}/messages` | Send a message and get response |
| `GET` | `/api/threads/{thread_id}/messages` | Get conversation history |

### Request/Response Examples

**Create Thread**

```http
POST /api/threads

{
  "metadata": {
    "user_id": "user_123",
    "session_type": "support"
  }
}
```

**Send Message**

```http
POST /api/threads/thread_xyz789/messages
Content-Type: application/json

{
  "content": "What's the weather in Seattle and calculate 15% tip on $85?"
}
```

**Response** (with tool usage)

```json
{
  "id": "msg_resp_456",
  "thread_id": "thread_xyz789",
  "role": "assistant",
  "content": "The weather in Seattle is 52°F with light rain. A 15% tip on $85 is $12.75.",
  "tool_calls": [
    {
      "tool": "get_weather",
      "arguments": {"location": "Seattle"},
      "result": {"temp": 52, "condition": "light rain"}
    },
    {
      "tool": "calculate",
      "arguments": {"expression": "85 * 0.15"},
      "result": 12.75
    }
  ],
  "timestamp": "2024-12-06T10:30:05Z"
}
```

## E2E Code Samples

### Basic Usage (Phase 1)

```python
from azure.identity import DefaultAzureCredential
from microsoft.agents.ai.azure import AzureOpenAIChatClient
from microsoft.agents.core import ChatAgent

# Initialize Azure OpenAI client
credential = DefaultAzureCredential()
chat_client = AzureOpenAIChatClient(
    endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
    model=os.environ["AZURE_OPENAI_MODEL"],
    credential=credential,
)

# Define tools - agent will decide when to use them
@ai_function
def get_weather(location: str) -> dict:
    """Get current weather for a location."""
    # Implementation here
    return {"temp": 52, "condition": "light rain", "location": location}

@ai_function
def calculate(expression: str) -> float:
    """Evaluate a mathematical expression."""
    # Safe evaluation implementation
    return eval(expression)  # Use safe_eval in production

@ai_function
def search_knowledge_base(query: str) -> list[dict]:
    """Search the knowledge base for relevant information."""
    # Could connect to Azure AI Search, Cosmos DB, etc.
    return [{"title": "...", "content": "..."}]

# Create agent with multiple tools
agent = ChatAgent(
    chat_client=chat_client,
    instructions="""You are a helpful assistant.
    Use the available tools when they can help answer the user's question.
    You can use multiple tools in a single response if needed.""",
    tools=[get_weather, calculate, search_knowledge_base],
)

# Agent autonomously decides which tools to use
response = await agent.run("What's the weather in NYC and what's 20% of 150?")
# Agent will call: get_weather("NYC") AND calculate("150 * 0.20")
```

### With Cosmos DB Persistence (Phase 2)

```python
from microsoft.agents.stores.cosmosdb import CosmosDBChatMessageStore

# Initialize Cosmos DB store
message_store = CosmosDBChatMessageStore(
    endpoint=os.environ["COSMOS_ENDPOINT"],
    database_name="chat_db",
    container_name="messages",
    credential=DefaultAzureCredential(),
)

# Create agent with persistent storage
agent = ChatAgent(
    chat_client=chat_client,
    instructions="...",
    tools=[get_weather, calculate, search_knowledge_base],
    message_store=message_store,  # Persistent storage
)

# Messages are automatically persisted
thread_id = "thread_abc123"
response = await agent.run(
    "What's the weather?",
    thread_id=thread_id,
)
```

### Azure Functions Integration (Phase 3)

```python
# function_app.py
import azure.functions as func
from microsoft.agents.ai.azure import AzureOpenAIChatClient
from microsoft.agents.core import ChatAgent
from microsoft.agents.stores.cosmosdb import CosmosDBChatMessageStore

app = func.FunctionApp()

# Singleton instances (reused across invocations)
chat_client = None
message_store = None
agent = None

def get_agent():
    global chat_client, message_store, agent
    if agent is None:
        chat_client = AzureOpenAIChatClient(...)
        message_store = CosmosDBChatMessageStore(...)
        agent = ChatAgent(
            chat_client=chat_client,
            tools=[get_weather, calculate, search_knowledge_base],
            message_store=message_store,
        )
    return agent

@app.route(route="threads/{thread_id}/messages", methods=["POST"])
async def send_message(req: func.HttpRequest) -> func.HttpResponse:
    thread_id = req.route_params.get("thread_id")
    body = req.get_json()

    agent = get_agent()
    response = await agent.run(
        body["content"],
        thread_id=thread_id,
    )

    return func.HttpResponse(
        body=json.dumps(response.to_dict()),
        mimetype="application/json",
    )
```

## Phased Implementation Plan

### Phase 1: Core Chat API with Cosmos DB Persistence ✅

**Goal**: Demonstrate runtime tool selection with persistent storage

- [x] Azure Functions HTTP triggers
- [x] Function tools (weather, calculator, knowledge base)
- [x] Cosmos DB thread and message persistence
- [x] `demo.http` file for testing
- [x] README with setup instructions
- [x] Infrastructure as Code (Bicep + azd)

**Files**:

```text
python/samples/demos/enterprise-chat-agent/
├── README.md
├── requirements.txt
├── local.settings.json.example
├── host.json
├── function_app.py
├── cosmos_store.py          # Cosmos DB conversation store
├── tools/
│   ├── __init__.py
│   ├── weather.py
│   ├── calculator.py
│   └── knowledge_base.py
├── demo.http
├── azure.yaml               # azd configuration
└── infra/
    ├── main.bicep
    ├── abbreviations.json
    └── core/
        ├── database/cosmos-nosql.bicep
        ├── host/function-app.bicep
        ├── monitor/monitoring.bicep
        └── storage/storage-account.bicep
```

### Phase 2: Agent Framework Integration (PR #2)

**Goal**: Integrate with Microsoft Agent Framework

- [ ] Replace placeholder logic with `ChatAgent`
- [ ] Azure OpenAI integration via Agent Framework
- [ ] Conversation history passed to agent for context
- [ ] Tool execution via Agent Framework runtime

### Phase 3: Production Hardening (PR #3)

**Goal**: Enterprise-ready patterns

- [ ] Managed Identity authentication
- [ ] OpenTelemetry tracing integration
- [ ] Structured logging
- [ ] Health check endpoint
- [ ] Retry policies and error handling

### Phase 4: Observability Dashboard (PR #4)

**Goal**: Operational visibility

- [ ] Application Insights integration
- [ ] Custom metrics (tokens, latency, tool usage)
- [ ] Sample Kusto queries
- [ ] Azure Dashboard template (optional)

### Phase 5: Redis Caching Extension (Future)

**Goal**: High-frequency access optimization

- [ ] Redis session cache
- [ ] Recent messages caching
- [ ] Rate limiting support

## Security Considerations

| Concern | Mitigation |
|---------|------------|
| **Authentication** | Azure AD / API Key via `X-API-Key` header |
| **Thread Isolation** | Cosmos DB partition key on `thread_id` |
| **Secrets Management** | Azure Key Vault for connection strings |
| **Network Security** | Private Endpoints for Cosmos DB & OpenAI |
| **Input Validation** | Pydantic models for request validation |

## Testing Strategy

1. **Unit Tests**: Tool functions, message store operations
2. **Integration Tests**: Cosmos DB emulator, Azure OpenAI mock
3. **E2E Tests**: Full API flow with `demo.http`
4. **Load Tests**: Azure Load Testing for scale validation

## Open Questions

1. **Package location**: Should `CosmosDBChatMessageStore` be a new package or part of existing `stores` package?
2. **Streaming support**: Should Phase 1 include SSE streaming responses?

## Appendix: Tool Selection Examples

### Example 1: Single Tool

```text
User: "What's the weather in Tokyo?"
Agent Decision: → get_weather("Tokyo")
Response: "The weather in Tokyo is 68°F and sunny."
```

### Example 2: Multiple Tools

```text
User: "What's the weather in Paris and what's 18% tip on €75?"
Agent Decision: → get_weather("Paris") + calculate("75 * 0.18")
Response: "Paris is 55°F with clouds. An 18% tip on €75 is €13.50."
```

### Example 3: No Tools Needed

```text
User: "Tell me a joke"
Agent Decision: → No tools (direct response)
Response: "Why don't scientists trust atoms? Because they make up everything!"
```

### Example 4: Tool Selection Based on Context

```text
User: "I need help with my order"
Agent Decision: → search_knowledge_base("order help support FAQ")
Response: "Based on our FAQ, here's how to check your order status..."
```
