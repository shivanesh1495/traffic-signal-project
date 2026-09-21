"""
Traffic Signal state and phase timing management.

Owns the signal state for a single intersection.
Enforces the complete state machine:

    NORMAL_GREEN  ──► NORMAL_YELLOW  ──► NORMAL_RED
         ▲                                   │
         └───────────────────────────────────┘
         │                                   │
    EMERGENCY_PREPARE ◄────────────────────◄─┘
         │
    EMERGENCY_GREEN
         │
    EMERGENCY_CLEAR
         │
    NORMAL_GREEN / NORMAL_RED (recovery schedule)

Transitions respect yellow and all-red safety durations.
"""
from __future__ import annotations

import logging
from typing import Optional

from backend.communication.schemas import SignalState

logger = logging.getLogger(__name__)

# Maximum seconds a signal stays in EMERGENCY_GREEN before self-recovering.
# This is a safety fallback — normally recovery is triggered by EMERGENCY_PASSED.
EMERGENCY_GREEN_TIMEOUT = 120.0


class SignalController:
    """
    State machine for a single traffic signal.

    Parameters
    ----------
    intersection_id : str
    green_seconds   : Normal green phase duration.
    yellow_seconds  : Yellow phase duration.
    all_red_seconds : All-red safety gap.
    cycle_offset    : Offset in seconds to stagger cycle starts.
    """

    def __init__(
        self,
        intersection_id: str,
        green_seconds: float = 30.0,
        yellow_seconds: float = 5.0,
        all_red_seconds: float = 2.0,
        cycle_offset: float = 0.0,
    ) -> None:
        self.intersection_id = intersection_id
        self._green = green_seconds
        self._yellow = yellow_seconds
        self._all_red = all_red_seconds

        # Initialise phase based on offset so signals aren't all synchronised
        self._state = SignalState.NORMAL_GREEN
        self._elapsed: float = 0.0
        self._skip_ahead(cycle_offset)

        # Emergency state tracking
        self._emergency_id: Optional[str] = None
        self._emergency_prepare_time: float = 0.0  # sim time when PREPARE entered
        self._emergency_eta: float = 0.0           # expected arrival sim time
        self._recovery_timer: float = 0.0

    def _skip_ahead(self, offset: float) -> None:
        """Fast-forward the signal phase by offset seconds to stagger starts."""
        if offset <= 0:
            return
        cycle = self._green + self._yellow + self._all_red
        if cycle <= 0:
            return
        offset = offset % cycle
        if offset < self._green:
            self._state = SignalState.NORMAL_GREEN
            self._elapsed = offset
        elif offset < self._green + self._yellow:
            self._state = SignalState.NORMAL_YELLOW
            self._elapsed = offset - self._green
        else:
            self._state = SignalState.NORMAL_RED
            self._elapsed = offset - self._green - self._yellow

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    @property
    def state(self) -> SignalState:
        return self._state

    @property
    def phase_elapsed(self) -> float:
        return self._elapsed

    @property
    def phase_remaining(self) -> float:
        """Seconds remaining in the current phase."""
        duration = self._phase_duration()
        remaining = duration - self._elapsed
        return max(0.0, remaining)

    def _phase_duration(self) -> float:
        mapping = {
            SignalState.NORMAL_GREEN: self._green,
            SignalState.NORMAL_YELLOW: self._yellow,
            SignalState.NORMAL_RED: self._all_red + self._green,  # red + next green wait
            SignalState.EMERGENCY_PREPARE: self._yellow + self._all_red,
            SignalState.EMERGENCY_GREEN: 0.0,   # held until PASSED — display 0 remaining
            SignalState.EMERGENCY_CLEAR: self._all_red,
        }
        return mapping.get(self._state, self._green)

    # ------------------------------------------------------------------
    # Tick update (normal operation)
    # ------------------------------------------------------------------

    def tick(self, dt: float) -> None:
        """Advance signal by dt seconds under normal operation rules."""
        self._elapsed += dt

        if self._state == SignalState.NORMAL_GREEN:
            if self._elapsed >= self._green:
                self._transition(SignalState.NORMAL_YELLOW)

        elif self._state == SignalState.NORMAL_YELLOW:
            if self._elapsed >= self._yellow:
                self._transition(SignalState.NORMAL_RED)

        elif self._state == SignalState.NORMAL_RED:
            red_total = self._all_red
            if self._elapsed >= red_total:
                self._transition(SignalState.NORMAL_GREEN)

        elif self._state == SignalState.EMERGENCY_PREPARE:
            # Hold in PREPARE until ETA arrives or max prepare time exceeded
            if self._elapsed >= self._yellow + self._all_red:
                # Safety time elapsed – activate green
                self._transition(SignalState.EMERGENCY_GREEN)

        elif self._state == SignalState.EMERGENCY_GREEN:
            # Normally held until EMERGENCY_PASSED is received.
            # Safety fallback: if PASSED was never delivered (e.g. start node
            # where EV departs immediately), self-recover after the timeout.
            if self._elapsed >= EMERGENCY_GREEN_TIMEOUT:
                logger.warning(
                    "[%s] EMERGENCY_GREEN safety timeout (%.0fs) – forcing recovery",
                    self.intersection_id,
                    self._elapsed,
                )
                self._transition(SignalState.EMERGENCY_CLEAR)
                self._emergency_id = None

        elif self._state == SignalState.EMERGENCY_CLEAR:
            if self._elapsed >= self._all_red:
                self._transition(SignalState.NORMAL_GREEN)
                self._emergency_id = None

    # ------------------------------------------------------------------
    # Emergency control
    # ------------------------------------------------------------------

    def prepare_emergency(self, emergency_id: str, eta: float, current_time: float) -> bool:
        """
        Signal is on the emergency route.  Prepare for green corridor.

        Returns True if the transition was accepted.
        """
        if self._state in (SignalState.EMERGENCY_GREEN, SignalState.EMERGENCY_PREPARE):
            # Already in emergency mode
            self._emergency_id = emergency_id
            self._emergency_eta = eta
            return True

        if self._state == SignalState.EMERGENCY_CLEAR:
            return False  # Recovery in progress; do not re-enter

        self._emergency_id = emergency_id
        self._emergency_eta = eta
        self._emergency_prepare_time = current_time
        self._transition(SignalState.EMERGENCY_PREPARE)
        logger.info(
            "[%s] EMERGENCY_PREPARE for %s (ETA %.1fs from now)",
            self.intersection_id,
            emergency_id,
            eta - current_time,
        )
        return True

    def activate_emergency_green(self, emergency_id: str) -> bool:
        """Force-activate EMERGENCY_GREEN (called when ETA is imminent)."""
        if self._emergency_id != emergency_id:
            return False
        if self._state in (SignalState.EMERGENCY_PREPARE, SignalState.NORMAL_RED):
            self._transition(SignalState.EMERGENCY_GREEN)
            logger.info("[%s] EMERGENCY_GREEN activated", self.intersection_id)
            return True
        return False

    def emergency_passed(self, emergency_id: str) -> bool:
        """Emergency vehicle has passed. Begin recovery."""
        if self._state not in (SignalState.EMERGENCY_GREEN, SignalState.EMERGENCY_PREPARE):
            return False
        if self._emergency_id != emergency_id and emergency_id != "*":
            return False
        self._transition(SignalState.EMERGENCY_CLEAR)
        logger.info("[%s] EMERGENCY_CLEAR – recovery started", self.intersection_id)
        return True

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _transition(self, new_state: SignalState) -> None:
        logger.debug(
            "[%s] %s -> %s",
            self.intersection_id,
            self._state.value,
            new_state.value,
        )
        self._state = new_state
        self._elapsed = 0.0

    # ------------------------------------------------------------------
    # Sensor function
    # ------------------------------------------------------------------

    def get_signal_state(self) -> SignalState:
        """Virtual sensor: read current signal state."""
        return self._state

    def reset(self, cycle_offset: float = 0.0) -> None:
        """Reset signal to initial state."""
        self._state = SignalState.NORMAL_GREEN
        self._elapsed = 0.0
        self._emergency_id = None
        self._skip_ahead(cycle_offset)
