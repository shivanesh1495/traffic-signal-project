"""
In-process asynchronous message bus for agent-to-agent communication.

Design:
- Agents post messages into per-recipient queues.
- At the end of each simulation tick the engine drains the queues and
  delivers messages to their intended recipients.
- Duplicate detection is based on message_id.
- Stale messages (older than stale_timeout) are silently dropped.
- All operations are synchronous within a tick so the simulation remains
  deterministic.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Callable, Dict, List, Optional, Set

from backend.communication.schemas import AgentMessage, MessageType

logger = logging.getLogger(__name__)


class MessageBus:
    """
    Central message bus for agent communication.

    Usage
    -----
    bus = MessageBus(stale_timeout=60)
    bus.register_handler("TSA-1", my_handler_fn)
    bus.post(message)
    delivered = bus.flush(current_time)   # called once per tick
    """

    def __init__(self, stale_timeout: float = 60.0) -> None:
        # queued messages per recipient
        self._queues: Dict[str, List[AgentMessage]] = defaultdict(list)
        # registered handler callbacks keyed by agent id
        self._handlers: Dict[str, Callable[[AgentMessage], None]] = {}
        # seen message IDs for duplicate protection
        self._seen_ids: Set[str] = set()
        self._stale_timeout = stale_timeout
        # full event log for inspection / API
        self._event_log: List[Dict] = []

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_handler(self, agent_id: str, handler: Callable[[AgentMessage], None]) -> None:
        """Register a handler function for an agent."""
        self._handlers[agent_id] = handler
        logger.debug("Registered handler for agent %s", agent_id)

    # ------------------------------------------------------------------
    # Posting
    # ------------------------------------------------------------------

    def post(self, message: AgentMessage) -> None:
        """Queue a message for delivery."""
        if message.message_id in self._seen_ids:
            logger.debug("Duplicate message %s dropped", message.message_id)
            return
        self._seen_ids.add(message.message_id)
        self._queues[message.receiver_id].append(message)
        logger.debug(
            "Message queued: %s -> %s [%s]",
            message.sender_id,
            message.receiver_id,
            message.type.value,
        )

    # ------------------------------------------------------------------
    # Delivery
    # ------------------------------------------------------------------

    def flush(self, current_time: float) -> int:
        """
        Deliver all pending messages.

        Stale messages (timestamp older than current_time - stale_timeout)
        are dropped and logged.

        Returns the number of messages successfully delivered.
        """
        delivered = 0
        stale_count = 0

        for agent_id, queue in list(self._queues.items()):
            handler = self._handlers.get(agent_id)
            pending = queue[:]
            queue.clear()

            for msg in pending:
                # Stale check applies only to emergency messages
                if msg.type in (
                    MessageType.EMERGENCY_PRIORITY,
                    MessageType.ROUTE_FORWARD,
                ):
                    age = current_time - msg.timestamp
                    if age > self._stale_timeout:
                        logger.warning(
                            "Stale message %s (age=%.1fs) dropped for agent %s",
                            msg.message_id,
                            age,
                            agent_id,
                        )
                        self._log_event(
                            current_time,
                            "STALE_MESSAGE",
                            msg.sender_id,
                            agent_id,
                            {"message_id": msg.message_id, "type": msg.type.value, "age": age},
                        )
                        stale_count += 1
                        continue

                if handler:
                    try:
                        handler(msg)
                        delivered += 1
                        self._log_event(
                            current_time,
                            msg.type.value,
                            msg.sender_id,
                            agent_id,
                            msg.payload,
                        )
                    except Exception as exc:  # noqa: BLE001
                        logger.error(
                            "Handler error for agent %s processing %s: %s",
                            agent_id,
                            msg.message_id,
                            exc,
                        )
                else:
                    logger.warning(
                        "No handler for agent %s – message %s dropped",
                        agent_id,
                        msg.message_id,
                    )

        if stale_count:
            logger.info("Dropped %d stale messages during flush", stale_count)

        return delivered

    # ------------------------------------------------------------------
    # Event log (for /api/events endpoint)
    # ------------------------------------------------------------------

    def _log_event(
        self,
        timestamp: float,
        event_type: str,
        sender: str,
        receiver: str,
        payload: object,
    ) -> None:
        self._event_log.append(
            {
                "timestamp": timestamp,
                "type": event_type,
                "sender": sender,
                "receiver": receiver,
                "payload": payload,
            }
        )
        # Keep log bounded
        if len(self._event_log) > 2000:
            self._event_log = self._event_log[-1000:]

    def get_event_log(self) -> List[Dict]:
        return list(self._event_log)

    def clear_event_log(self) -> None:
        self._event_log.clear()

    def reset(self) -> None:
        """Reset bus state (used on simulation reset)."""
        self._queues.clear()
        self._seen_ids.clear()
        self._event_log.clear()
        logger.info("MessageBus reset")
