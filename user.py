"""User class mapped to the user table."""


class User:
    """Represents a system user account."""
    # User owns Ticket records (one-to-many).
    # DEMO NOTE: This mirrors the `user` table used for login and account roles.

    # prompt: initialize a user entity matching the user table structure
    def __init__(self, user_id: int, username: str, password: str, admin: bool) -> None:
        """Store user identity, username, password hash, and admin role."""
        self.id = user_id
        self.username = username
        self.password = password
        self.admin = admin
