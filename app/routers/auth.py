"""Backward-compatible authentication import surface.

The database-backed router is the single implementation. Older workers and
tests may still import ``app.routers.auth.get_current_user``.
"""

from app.routers.auth_db import get_current_user

__all__ = ["get_current_user"]
