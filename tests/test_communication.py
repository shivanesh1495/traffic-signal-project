"""
Tests for agent-to-agent communication protocol.

Acceptance criteria:
- Messages are created with required fields.
- Messages are delivered to correct recipients.
- ACK messages are generated.
- Stale emergency messages are dropped.
- Duplicate messages do not cause duplicate actions.
- Agents only act on messages for their intersection/neighbours.
"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.communication.message_bus import MessageBus
from backend.communication.schemas import (
    AgentMessage,
    MessageType,
    SignalState,
    TrafficUpdatePayload,
    EmergencyPriorityPayload,
    EmergencyPriority,
    EmergencyPassedPayload,
    VehicleType,
)


@pytest.fixture
def bus():
    return MessageBus(stale_timeout=30.0)


class TestMessageCreation:
    def test_message_has_unique_id(self):
        m1 = AgentMessage(
            type=MessageType.TRAFFIC_UPDATE,
            sender_id="TSA-1",
            receiver_id="TSA-2",
            timestamp=0.0,
            payload={},
        )
        m2 = AgentMessage(
            type=MessageType.TRAFFIC_UPDATE,
            sender_id="TSA-1",
            receiver_id="TSA-2",
            timestamp=0.0,
            payload={},
        )
        assert m1.message_id != m2.message_id

    def test_traffic_update_payload_fields(self):
        payload = TrafficUpdatePayload(
            vehicle_count=8,
            queue_length=3,
            signal_state=SignalState.NORMAL_RED,
            congestion_ratio=0.62,
            average_speed=22.0,
        )
        assert payload.vehicle_count == 8
        assert payload.queue_length == 3
        assert payload.congestion_ratio == 0.62

    def test_emergency_priority_payload_fields(self):
        payload = EmergencyPriorityPayload(
            emergency_id="EV01",
            route=["I1", "I2", "I4", "I5"],
            priority=EmergencyPriority.HIGH,
            eta_to_intersection={"I2": 8.0, "I4": 16.0, "I5": 25.0},
            vehicle_type=VehicleType.AMBULANCE,
        )
        assert payload.emergency_id == "EV01"
        assert len(payload.route) == 4
        assert payload.eta_to_intersection["I2"] == 8.0


class TestMessageDelivery:
    def test_message_delivered_to_registered_handler(self, bus):
        received = []
        bus.register_handler("TSA-2", received.append)

        msg = AgentMessage(
            type=MessageType.TRAFFIC_UPDATE,
            sender_id="TSA-1",
            receiver_id="TSA-2",
            timestamp=0.0,
            payload={"vehicle_count": 5},
        )
        bus.post(msg)
        delivered = bus.flush(current_time=0.0)

        assert delivered == 1
        assert len(received) == 1
        assert received[0].message_id == msg.message_id

    def test_message_not_delivered_without_handler(self, bus):
        msg = AgentMessage(
            type=MessageType.TRAFFIC_UPDATE,
            sender_id="TSA-1",
            receiver_id="TSA-NO_HANDLER",
            timestamp=0.0,
            payload={},
        )
        bus.post(msg)
        delivered = bus.flush(0.0)
        assert delivered == 0

    def test_multiple_recipients(self, bus):
        received_2, received_3 = [], []
        bus.register_handler("TSA-2", received_2.append)
        bus.register_handler("TSA-3", received_3.append)

        for rid in ["TSA-2", "TSA-3"]:
            bus.post(AgentMessage(
                type=MessageType.TRAFFIC_UPDATE,
                sender_id="TSA-1",
                receiver_id=rid,
                timestamp=0.0,
                payload={},
            ))

        bus.flush(0.0)
        assert len(received_2) == 1
        assert len(received_3) == 1


class TestStaleMessages:
    def test_stale_emergency_message_dropped(self, bus):
        received = []
        bus.register_handler("TSA-2", received.append)

        # Post message with timestamp=0, flush at time=100 (stale_timeout=30)
        msg = AgentMessage(
            type=MessageType.EMERGENCY_PRIORITY,
            sender_id="EV01",
            receiver_id="TSA-2",
            timestamp=0.0,
            payload=EmergencyPriorityPayload(
                emergency_id="EV01",
                route=["I1", "I2"],
                priority=EmergencyPriority.HIGH,
                eta_to_intersection={"I2": 10.0},
            ).model_dump(),
        )
        bus.post(msg)
        delivered = bus.flush(current_time=100.0)  # age = 100s > 30s timeout

        assert delivered == 0
        assert len(received) == 0

    def test_fresh_emergency_message_delivered(self, bus):
        received = []
        bus.register_handler("TSA-2", received.append)

        msg = AgentMessage(
            type=MessageType.EMERGENCY_PRIORITY,
            sender_id="EV01",
            receiver_id="TSA-2",
            timestamp=5.0,
            payload=EmergencyPriorityPayload(
                emergency_id="EV01",
                route=["I1", "I2"],
                priority=EmergencyPriority.HIGH,
                eta_to_intersection={"I2": 15.0},
            ).model_dump(),
        )
        bus.post(msg)
        delivered = bus.flush(current_time=10.0)  # age = 5s < 30s timeout

        assert delivered == 1
        assert len(received) == 1

    def test_traffic_updates_not_affected_by_stale_check(self, bus):
        """TRAFFIC_UPDATE messages are not subject to stale-message drops."""
        received = []
        bus.register_handler("TSA-2", received.append)

        msg = AgentMessage(
            type=MessageType.TRAFFIC_UPDATE,
            sender_id="TSA-1",
            receiver_id="TSA-2",
            timestamp=0.0,
            payload={"vehicle_count": 5, "queue_length": 2,
                     "signal_state": "NORMAL_RED", "congestion_ratio": 0.3},
        )
        bus.post(msg)
        delivered = bus.flush(current_time=9999.0)

        assert delivered == 1


class TestDuplicateMessages:
    def test_duplicate_message_not_delivered_twice(self, bus):
        received = []
        bus.register_handler("TSA-2", received.append)

        msg = AgentMessage(
            type=MessageType.TRAFFIC_UPDATE,
            sender_id="TSA-1",
            receiver_id="TSA-2",
            timestamp=0.0,
            payload={},
        )
        bus.post(msg)
        bus.post(msg)  # same message_id – duplicate
        bus.flush(0.0)

        assert len(received) == 1, "Duplicate message must only be delivered once"

    def test_different_messages_both_delivered(self, bus):
        received = []
        bus.register_handler("TSA-2", received.append)

        for _ in range(3):
            bus.post(AgentMessage(
                type=MessageType.TRAFFIC_UPDATE,
                sender_id="TSA-1",
                receiver_id="TSA-2",
                timestamp=0.0,
                payload={},
            ))
        bus.flush(0.0)
        assert len(received) == 3  # 3 distinct message IDs


class TestEventLog:
    def test_event_log_populated(self, bus):
        received = []
        bus.register_handler("TSA-2", received.append)
        bus.post(AgentMessage(
            type=MessageType.TRAFFIC_UPDATE,
            sender_id="TSA-1",
            receiver_id="TSA-2",
            timestamp=0.0,
            payload={},
        ))
        bus.flush(0.0)
        log = bus.get_event_log()
        assert len(log) >= 1
        assert log[0]["sender"] == "TSA-1"
        assert log[0]["receiver"] == "TSA-2"

    def test_bus_reset_clears_state(self, bus):
        bus.post(AgentMessage(
            type=MessageType.TRAFFIC_UPDATE,
            sender_id="TSA-1",
            receiver_id="TSA-2",
            timestamp=0.0,
            payload={},
        ))
        bus.reset()
        assert bus.get_event_log() == []
