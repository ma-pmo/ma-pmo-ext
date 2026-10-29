"""Resource calendar connector (stub). Placeholder for Google/MS Calendar — used by A3."""
from __future__ import annotations


class CalendarConnector:
    def get_availability(self, resource_id: str, week: str) -> float:
        """Available hours in the given week. TODO: real calendar integration."""
        raise NotImplementedError("to be implemented in phase P3 (resources/planning)")
