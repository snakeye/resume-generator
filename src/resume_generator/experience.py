"""Deterministic work-history grouping for resume generation stages."""

from __future__ import annotations

from dataclasses import dataclass

from .profile import Profile


@dataclass(frozen=True)
class ExperienceGroup:
    """A set of source work indexes sharing one presentation policy."""

    work_indexes: tuple[int, ...]
    earlier: bool = False


def experience_groups(profile: Profile) -> tuple[ExperienceGroup, ...]:
    """Return detailed positions and one optional Earlier Experience group."""
    preference = profile.preferences.earlier_experience
    if preference is None:
        return tuple(ExperienceGroup((index,)) for index in range(len(profile.work)))

    earlier_indexes = _earlier_indexes(profile)
    if not earlier_indexes:
        return tuple(ExperienceGroup((index,)) for index in range(len(profile.work)))
    earlier = set(earlier_indexes)
    groups = tuple(ExperienceGroup((index,)) for index in range(len(profile.work)) if index not in earlier)
    return (*groups, ExperienceGroup(tuple(earlier_indexes), earlier=True))


def _earlier_indexes(profile: Profile) -> tuple[int, ...]:
    preference = profile.preferences.earlier_experience
    assert preference is not None
    if preference.detailed_positions is not None:
        start = preference.detailed_positions
        return tuple(range(start, len(profile.work)))
    assert preference.ending_before is not None
    indexes = tuple(
        index
        for index, work in enumerate(profile.work)
        if work.end_date is not None and _date_key(work.end_date) < _date_key(preference.ending_before)
    )
    if indexes and indexes != tuple(range(indexes[0], len(profile.work))):
        raise ValueError("earlier experience positions must form the oldest contiguous work-history tail")
    return indexes


def _date_key(value: str) -> tuple[int, int]:
    year, _, month = value.partition("-")
    return int(year), int(month or 12)
