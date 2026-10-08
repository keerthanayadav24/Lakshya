"""Exceptions for Lakshya deterministic study planner."""


class SchedulingImpossible(Exception):
    """Raised when study tasks cannot fit before deadline under policy."""

    pass
