"""Ticket class mapped to the ticket table."""


class Ticket:
    """Represents a booking; number is its seat quantity, not a seat identifier."""
    # Ticket links one User to one Run (booking relationship).
    # NOTE: In Part 2, `number` stores quantity in one booking row.

    # initialize a ticket entity matching the ticket table structure
    def __init__(self, ticket_id: int, user_id: int, run_id: int, number: int) -> None:
        """Store ticket identity, owner, run, and positive quantity of seats booked."""
        self.id = ticket_id
        self.user_id = user_id
        self.run_id = run_id
        self.number = number
