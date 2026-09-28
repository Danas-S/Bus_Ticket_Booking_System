"""Service class mapped to the service table."""


class Service:
    """Represents a scheduled route service."""
    # Service links to many Run rows and assigned Bus rows.
    # NOTE: Admin-created services appear immediately in customer booking lists.

    # initialize a service entity matching the service table structure
    def __init__(self, service_id: int, name: str) -> None:
        """Store service identity and route/time description."""
        self.id = service_id
        self.name = name
