# Copyright (c) Microsoft. All rights reserved.
"""
Cosmos DB Storage for Threads and Messages

This module provides persistent storage for conversation threads and messages
using Azure Cosmos DB with thread_id as the partition key.

Document Types:
- Thread: {"type": "thread", "id": "thread_xxx", "thread_id": "thread_xxx", ...}
- Message: {"type": "message", "id": "msg_xxx", "thread_id": "thread_xxx", ...}
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any

from azure.cosmos import CosmosClient, PartitionKey
from azure.cosmos.exceptions import CosmosResourceNotFoundError
from azure.identity import DefaultAzureCredential


class CosmosConversationStore:
    """
    Manages conversation threads and messages in Azure Cosmos DB.

    Uses a single container with thread_id as partition key.
    Documents are differentiated by 'type' field: 'thread' or 'message'.
    """

    def __init__(
        self,
        endpoint: str | None = None,
        database_name: str | None = None,
        container_name: str | None = None,
        credential: Any | None = None,
    ):
        """
        Initialize the Cosmos DB conversation store.

        Args:
            endpoint: Cosmos DB endpoint URL. Defaults to AZURE_COSMOS_ENDPOINT env var.
            database_name: Database name. Defaults to AZURE_COSMOS_DATABASE_NAME env var.
            container_name: Container name. Defaults to AZURE_COSMOS_CONTAINER_NAME env var.
            credential: Azure credential. Defaults to DefaultAzureCredential.
        """
        self.endpoint = endpoint or os.environ.get("AZURE_COSMOS_ENDPOINT")
        self.database_name = database_name or os.environ.get(
            "AZURE_COSMOS_DATABASE_NAME", "chat_db"
        )
        self.container_name = container_name or os.environ.get(
            "AZURE_COSMOS_CONTAINER_NAME", "messages"
        )

        if not self.endpoint:
            raise ValueError(
                "Cosmos DB endpoint is required. "
                "Set AZURE_COSMOS_ENDPOINT environment variable."
            )

        self.credential = credential or DefaultAzureCredential()
        self._client: CosmosClient | None = None
        self._container = None

    @property
    def container(self):
        """Lazy initialization of Cosmos DB container client."""
        if self._container is None:
            self._client = CosmosClient(self.endpoint, credential=self.credential)
            database = self._client.get_database_client(self.database_name)
            self._container = database.get_container_client(self.container_name)
        return self._container

    # -------------------------------------------------------------------------
    # Thread Operations
    # -------------------------------------------------------------------------

    async def create_thread(
        self,
        thread_id: str,
        user_id: str,
        title: str | None = None,
        metadata: dict | None = None,
    ) -> dict:
        """
        Create a new conversation thread.

        Args:
            thread_id: Unique thread identifier.
            user_id: Owner's user ID.
            title: Optional thread title.
            metadata: Optional custom metadata.

        Returns:
            The created thread document.
        """
        now = datetime.now(timezone.utc).isoformat()
        thread = {
            "id": thread_id,
            "thread_id": thread_id,  # Partition key
            "type": "thread",
            "user_id": user_id,
            "title": title,
            "status": "active",
            "message_count": 0,
            "created_at": now,
            "updated_at": now,
            "last_message_preview": None,
            "metadata": metadata or {},
        }

        self.container.create_item(body=thread)
        logging.info(f"Created thread {thread_id} for user {user_id} in Cosmos DB")
        return thread

    async def get_thread(self, thread_id: str) -> dict | None:
        """
        Get a thread by ID.

        Args:
            thread_id: Thread identifier.

        Returns:
            Thread document or None if not found.
        """
        try:
            thread = self.container.read_item(
                item=thread_id,
                partition_key=thread_id,
            )
            return thread
        except CosmosResourceNotFoundError:
            return None

    async def delete_thread(self, thread_id: str) -> bool:
        """
        Delete a thread and all its messages.

        Args:
            thread_id: Thread identifier.

        Returns:
            True if deleted, False if not found.
        """
        # First, get all items in the partition (thread + messages)
        query = "SELECT c.id FROM c WHERE c.thread_id = @thread_id"
        items = list(
            self.container.query_items(
                query=query,
                parameters=[{"name": "@thread_id", "value": thread_id}],
                partition_key=thread_id,
            )
        )

        if not items:
            return False

        # Delete all items in the partition
        for item in items:
            self.container.delete_item(item=item["id"], partition_key=thread_id)

        logging.info(f"Deleted thread {thread_id} and {len(items)} items from Cosmos DB")
        return True

    # -------------------------------------------------------------------------
    # Message Operations
    # -------------------------------------------------------------------------

    async def add_message(
        self,
        thread_id: str,
        message_id: str,
        role: str,
        content: str,
        tool_calls: list[dict] | None = None,
        sources: list[dict] | None = None,
        metadata: dict | None = None,
    ) -> dict:
        """
        Add a message to a thread and update thread metadata.

        Args:
            thread_id: Thread identifier (partition key).
            message_id: Unique message identifier.
            role: Message role ('user', 'assistant', or 'system').
            content: Message content.
            tool_calls: Optional list of tool calls made by the agent.
            sources: Optional RAG sources (for assistant messages).
            metadata: Optional custom metadata.

        Returns:
            The created message document.
        """
        message = {
            "id": message_id,
            "message_id": message_id,
            "thread_id": thread_id,  # Partition key
            "type": "message",
            "role": role,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tool_calls": tool_calls,
            "sources": sources,
            "metadata": metadata or {},
        }

        self.container.create_item(body=message)
        logging.info(f"Added {role} message {message_id} to thread {thread_id}")

        # Update thread metadata
        thread = await self.get_thread(thread_id)
        if thread:
            # Truncate content for preview (first 100 chars)
            preview = content[:100] + "..." if len(content) > 100 else content
            await self.update_thread(
                thread_id=thread_id,
                message_count=thread.get("message_count", 0) + 1,
                last_message_preview=preview,
            )

        return message

    async def get_messages(
        self,
        thread_id: str,
        limit: int = 100,
    ) -> list[dict]:
        """
        Get all messages in a thread, ordered by timestamp.

        Args:
            thread_id: Thread identifier.
            limit: Maximum number of messages to return.

        Returns:
            List of message documents.
        """
        query = """
            SELECT * FROM c
            WHERE c.thread_id = @thread_id AND c.type = 'message'
            ORDER BY c.timestamp ASC
        """

        messages = list(
            self.container.query_items(
                query=query,
                parameters=[{"name": "@thread_id", "value": thread_id}],
                partition_key=thread_id,
                max_item_count=limit,
            )
        )

        return messages

    async def update_thread(
        self,
        thread_id: str,
        title: str | None = None,
        status: str | None = None,
        message_count: int | None = None,
        last_message_preview: str | None = None,
    ) -> dict | None:
        """
        Update thread metadata.

        Args:
            thread_id: Thread identifier.
            title: New title (optional).
            status: New status - 'active', 'archived', or 'deleted' (optional).
            message_count: New message count (optional).
            last_message_preview: Preview of last message (optional).

        Returns:
            Updated thread document or None if not found.
        """
        thread = await self.get_thread(thread_id)
        if thread is None:
            return None

        # Update fields
        if title is not None:
            thread["title"] = title
        if status is not None:
            thread["status"] = status
        if message_count is not None:
            thread["message_count"] = message_count
        if last_message_preview is not None:
            thread["last_message_preview"] = last_message_preview

        thread["updated_at"] = datetime.now(timezone.utc).isoformat()

        updated = self.container.replace_item(item=thread_id, body=thread)
        logging.info(f"Updated thread {thread_id}")
        return updated

    async def thread_exists(self, thread_id: str) -> bool:
        """
        Check if a thread exists.

        Args:
            thread_id: Thread identifier.

        Returns:
            True if thread exists, False otherwise.
        """
        thread = await self.get_thread(thread_id)
        return thread is not None
