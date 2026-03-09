"""AppContext — shared context passed to all panels."""

from __future__ import annotations

from dataclasses import dataclass, field

from jig.core.timeline import TimelineController


@dataclass
class AppContext:
    """Holds references to shared application state.

    Passed to every PanelBase so panels can access the timeline,
    active sessions, and the combined DataStore.
    """

    timeline: TimelineController
    sessions: list = field(default_factory=list)  # list[Session]

    @property
    def active_data_store(self):
        """Return the DataStore from the first session, or None."""
        from jig.core.data_store import DataStore

        if self.sessions:
            return self.sessions[0].data_store
        return None
