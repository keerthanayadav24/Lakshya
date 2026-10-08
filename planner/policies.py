"""Scheduling policy definition and validation for Lakshya deterministic planner."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SchedulingPolicy:
    """Policy rules for deterministic study block placement."""

    max_daily_minutes: int = 240
    study_block_minutes: int = 50
    break_minutes: int = 10
    mandatory_rest_start_hour: int = 22
    mandatory_rest_end_hour: int = 7


def validate_policy(policy: SchedulingPolicy) -> None:
    """Validate that scheduling policy constraints are coherent and non-zero."""
    if policy.max_daily_minutes <= 0:
        raise ValueError("max_daily_minutes must be greater than 0")
    if policy.study_block_minutes <= 0:
        raise ValueError("study_block_minutes must be greater than 0")
    if policy.break_minutes < 0:
        raise ValueError("break_minutes cannot be negative")
    if not (0 <= policy.mandatory_rest_start_hour <= 23):
        raise ValueError("mandatory_rest_start_hour must be between 0 and 23")
    if not (0 <= policy.mandatory_rest_end_hour <= 23):
        raise ValueError("mandatory_rest_end_hour must be between 0 and 23")
    if policy.study_block_minutes > 1440:
        raise ValueError("study_block_minutes cannot exceed 1440 minutes")
    if policy.study_block_minutes > policy.max_daily_minutes:
        raise ValueError("study_block_minutes cannot exceed max_daily_minutes")
