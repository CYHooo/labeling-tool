"""Who is using the tool: the sign-in step in front of the labeling screens.

The login dialog only talks to an `Authenticator`. Until the server has an
account system, `DevAuthenticator` accepts the single development account
admin / admin -- a placeholder written into the client, NOT security. When
the server gains accounts, add an Authenticator that asks it and return it
from default_authenticator(); the dialog does not change.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class User:
    user_id: str


class AuthError(Exception):
    """Wrong ID or password (the message never says which)."""


class Authenticator(Protocol):
    def login(self, user_id: str, password: str) -> User:
        """The signed-in user, or AuthError."""


class DevAuthenticator:
    """The development account only: admin / admin."""

    ACCOUNTS = {"admin": "admin"}

    def login(self, user_id: str, password: str) -> User:
        uid = (user_id or "").strip()
        if not uid or self.ACCOUNTS.get(uid) != password:
            raise AuthError("incorrect ID or password")
        return User(uid)


def default_authenticator() -> Authenticator:
    return DevAuthenticator()
