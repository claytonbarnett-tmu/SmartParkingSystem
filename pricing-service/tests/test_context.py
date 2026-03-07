"""Tests for the context-building helpers in bandit.py.

These are pure functions with no database dependency.
"""

from datetime import datetime

from pricing.bandit import (
    ALL_CONTEXT_KEYS,
    DEFAULT_MULTIPLIERS,
    _day_type,
    _occupancy_bucket,
    _time_bucket,
    build_context_key,
)


# ── _time_bucket ──────────────────────────────────────────────────────────


class TestTimeBucket:
    def test_morning_start(self):
        assert _time_bucket(6) == "morning"

    def test_morning_end(self):
        assert _time_bucket(10) == "morning"

    def test_afternoon_start(self):
        assert _time_bucket(11) == "afternoon"

    def test_afternoon_end(self):
        assert _time_bucket(15) == "afternoon"

    def test_evening_start(self):
        assert _time_bucket(16) == "evening"

    def test_evening_end(self):
        assert _time_bucket(20) == "evening"

    def test_night_late(self):
        assert _time_bucket(23) == "night"

    def test_night_early(self):
        assert _time_bucket(3) == "night"

    def test_midnight(self):
        assert _time_bucket(0) == "night"

    def test_night_boundary_21(self):
        assert _time_bucket(21) == "night"


# ── _day_type ─────────────────────────────────────────────────────────────


class TestDayType:
    def test_monday_is_weekday(self):
        assert _day_type(datetime(2026, 3, 2)) == "weekday"  # Monday

    def test_friday_is_weekday(self):
        assert _day_type(datetime(2026, 3, 6)) == "weekday"  # Friday

    def test_saturday_is_weekend(self):
        assert _day_type(datetime(2026, 3, 7)) == "weekend"  # Saturday

    def test_sunday_is_weekend(self):
        assert _day_type(datetime(2026, 3, 8)) == "weekend"  # Sunday


# ── _occupancy_bucket ─────────────────────────────────────────────────────


class TestOccupancyBucket:
    def test_zero_is_low(self):
        assert _occupancy_bucket(0.0) == "low"

    def test_below_30_is_low(self):
        assert _occupancy_bucket(0.29) == "low"

    def test_exactly_30_is_medium(self):
        assert _occupancy_bucket(0.30) == "medium"

    def test_mid_range_is_medium(self):
        assert _occupancy_bucket(0.50) == "medium"

    def test_exactly_70_is_medium(self):
        assert _occupancy_bucket(0.70) == "medium"

    def test_above_70_is_high(self):
        assert _occupancy_bucket(0.71) == "high"

    def test_full_is_high(self):
        assert _occupancy_bucket(1.0) == "high"


# ── build_context_key ─────────────────────────────────────────────────────


class TestBuildContextKey:
    def test_morning_weekday_high(self):
        dt = datetime(2026, 3, 4, 9, 0)  # Wednesday 9 AM
        assert build_context_key(dt, 0.82) == "morning:weekday:high"

    def test_night_weekend_low(self):
        dt = datetime(2026, 3, 7, 22, 0)  # Saturday 10 PM
        assert build_context_key(dt, 0.15) == "night:weekend:low"

    def test_afternoon_weekday_medium(self):
        dt = datetime(2026, 3, 3, 13, 30)  # Tuesday 1:30 PM
        assert build_context_key(dt, 0.55) == "afternoon:weekday:medium"

    def test_evening_weekend_high(self):
        dt = datetime(2026, 3, 8, 19, 0)  # Sunday 7 PM
        assert build_context_key(dt, 0.90) == "evening:weekend:high"


# ── Constants ─────────────────────────────────────────────────────────────


class TestConstants:
    def test_all_context_keys_count(self):
        assert len(ALL_CONTEXT_KEYS) == 24

    def test_all_context_keys_unique(self):
        assert len(set(ALL_CONTEXT_KEYS)) == 24

    def test_default_multipliers_count(self):
        assert len(DEFAULT_MULTIPLIERS) == 6

    def test_default_multipliers_sorted(self):
        assert DEFAULT_MULTIPLIERS == sorted(DEFAULT_MULTIPLIERS)

    def test_multiplier_1_is_present(self):
        assert 1.00 in DEFAULT_MULTIPLIERS
