"""BusModel class mapped to the bus_model table."""


class BusModel:
    """Represents a bus type and seat capacity."""
    # BusModel is referenced by Bus to define seat capacity.
    # NOTE: Seat capacity drives availability shown in customer run listings.

    # initialize a bus model entity matching the bus_model table structure
    def __init__(self, model_id: int, name: str, seats: int) -> None:
        """Store model identity, label, and seating capacity."""
        self.id = model_id
        self.name = name
        self.seats = seats
