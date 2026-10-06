"""Behaviour tests for the fixed offset table kernel.

Run them from the project root:

    python3 -m unittest discover -s tests -v

Every call into the kernel goes through a helper: a conversion that has to
work is asserted to work, and a conversion that has to be refused is
asserted to be refused.  A kernel that raises where it should answer, or
answers where it should raise, fails an assertion here -- it never lets an
exception escape the case.
"""

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from localtime.core import (
    CoverageError,
    GapError,
    OffsetTable,
    TableError,
    TimeZoneError,
    local_to_utc,
    utc_to_local,
)

HOUR = timedelta(hours=1)

#: Eastern time for 2025 and 2026, with the real changeover instants.
EASTERN = OffsetTable(
    (
        (datetime(2025, 1, 1, 0, 0), -5 * HOUR, "EST"),
        (datetime(2025, 3, 9, 7, 0), -4 * HOUR, "EDT"),
        (datetime(2025, 11, 2, 6, 0), -5 * HOUR, "EST"),
        (datetime(2026, 3, 8, 7, 0), -4 * HOUR, "EDT"),
        (datetime(2026, 11, 1, 6, 0), -5 * HOUR, "EST"),
    )
)


def raw_to_local(instant):
    """utc_to_local called straight through, for the refusal cases."""
    return utc_to_local(EASTERN, instant)


def raw_to_utc(reading, fold=0):
    """local_to_utc called straight through, for the refusal cases."""
    return local_to_utc(EASTERN, reading, fold)


class KernelCase(unittest.TestCase):
    """Helpers that keep every outcome of a kernel call inside an assertion."""

    def to_local(self, instant):
        """The wall clock reading of a UTC instant; a refusal fails the case."""
        try:
            return utc_to_local(EASTERN, instant)
        except Exception as error:
            self.fail(
                "utc_to_local(%s) raised %s: %s" % (instant, type(error).__name__, error)
            )

    def to_utc(self, reading, fold=0):
        """The UTC instant of a wall clock reading; a refusal fails the case."""
        try:
            return local_to_utc(EASTERN, reading, fold)
        except Exception as error:
            self.fail(
                "local_to_utc(%s, fold=%r) raised %s: %s"
                % (reading, fold, type(error).__name__, error)
            )

    def refuses(self, error_type, function, *args):
        """Assert that *function* refuses this call with *error_type*."""
        label = "%s(%s)" % (
            getattr(function, "__name__", repr(function)),
            ", ".join(repr(argument) for argument in args),
        )
        try:
            returned = function(*args)
        except error_type as error:
            self.assertIsInstance(error, ValueError)
            return
        except Exception as error:
            self.fail(
                "%s raised %s: %s, expected %s"
                % (label, type(error).__name__, error, error_type.__name__)
            )
        self.fail("%s returned %r, expected %s" % (label, returned, error_type.__name__))


class ReadingTest(KernelCase):
    def test_the_offset_in_force_produces_the_reading(self):
        self.assertEqual(self.to_local(datetime(2025, 1, 15, 12, 0)), datetime(2025, 1, 15, 7, 0))
        self.assertEqual(self.to_local(datetime(2025, 7, 15, 12, 0)), datetime(2025, 7, 15, 8, 0))
        self.assertEqual(self.to_local(datetime(2026, 1, 15, 12, 0)), datetime(2026, 1, 15, 7, 0))
        self.assertEqual(self.to_local(datetime(2026, 7, 15, 12, 0)), datetime(2026, 7, 15, 8, 0))
        self.assertEqual(self.to_utc(datetime(2025, 1, 15, 7, 0)), datetime(2025, 1, 15, 12, 0))
        self.assertEqual(self.to_utc(datetime(2025, 7, 15, 8, 0)), datetime(2025, 7, 15, 12, 0))
        self.assertEqual(EASTERN.name_at(datetime(2025, 1, 15, 12, 0)), "EST")
        self.assertEqual(EASTERN.name_at(datetime(2025, 7, 15, 12, 0)), "EDT")


class ChangeoverTest(KernelCase):
    def test_a_changeover_instant_belongs_to_the_offset_it_starts(self):
        self.assertEqual(
            self.to_local(datetime(2025, 3, 9, 6, 59, 59)), datetime(2025, 3, 9, 1, 59, 59)
        )
        self.assertEqual(self.to_local(datetime(2025, 3, 9, 7, 0)), datetime(2025, 3, 9, 3, 0))
        self.assertEqual(
            self.to_local(datetime(2025, 3, 9, 7, 0, 0, 1)), datetime(2025, 3, 9, 3, 0, 0, 1)
        )
        self.assertEqual(
            self.to_local(datetime(2025, 11, 2, 5, 59, 59)), datetime(2025, 11, 2, 1, 59, 59)
        )
        self.assertEqual(self.to_local(datetime(2025, 11, 2, 6, 0)), datetime(2025, 11, 2, 1, 0))
        self.assertEqual(self.to_local(datetime(2026, 3, 8, 7, 0)), datetime(2026, 3, 8, 3, 0))
        self.assertEqual(self.to_local(datetime(2026, 11, 1, 6, 0)), datetime(2026, 11, 1, 1, 0))
        self.assertEqual(self.to_utc(datetime(2025, 11, 2, 1, 0)), datetime(2025, 11, 2, 5, 0))


class RoundTripTest(KernelCase):
    def test_utc_and_local_readings_are_inverse(self):
        probes = []
        step = timedelta(minutes=45)
        moment = datetime(2025, 1, 1, 0, 0)
        while moment < datetime(2026, 1, 1, 0, 0):
            probes.append(moment)
            moment += step
        probes += [
            datetime(2025, 1, 1, 0, 0, 1),
            datetime(2025, 6, 7, 8, 9, 43),
            datetime(2025, 12, 31, 23, 59, 59),
            datetime(2026, 1, 1, 4, 30, 15),
        ]
        for instant in probes:
            if datetime(2025, 11, 2, 5, 0) <= instant < datetime(2025, 11, 2, 7, 0):
                # the hour that runs twice has two instants per reading
                continue
            with self.subTest(instant=instant):
                self.assertEqual(self.to_local(self.to_utc(self.to_local(instant))), self.to_local(instant))
                self.assertEqual(self.to_utc(self.to_local(instant)), instant)


class RepeatedHourTest(KernelCase):
    def test_readings_inside_the_repeated_hour_pick_a_side(self):
        self.assertEqual(self.to_utc(datetime(2025, 11, 2, 1, 30)), datetime(2025, 11, 2, 5, 30))
        self.assertEqual(self.to_utc(datetime(2025, 11, 2, 1, 30), 1), datetime(2025, 11, 2, 6, 30))
        self.assertEqual(self.to_utc(datetime(2025, 11, 2, 1, 0)), datetime(2025, 11, 2, 5, 0))
        self.assertEqual(self.to_utc(datetime(2025, 11, 2, 1, 0), 1), datetime(2025, 11, 2, 6, 0))
        self.assertEqual(
            self.to_utc(datetime(2025, 11, 2, 1, 45, 30)), datetime(2025, 11, 2, 5, 45, 30)
        )
        self.assertEqual(self.to_utc(datetime(2025, 11, 2, 2, 0)), datetime(2025, 11, 2, 7, 0))
        self.assertEqual(self.to_utc(datetime(2025, 11, 2, 2, 0), 1), datetime(2025, 11, 2, 7, 0))
        self.assertEqual(self.to_local(datetime(2025, 11, 2, 6, 30)), datetime(2025, 11, 2, 1, 30))


class MissingHourTest(KernelCase):
    def test_readings_inside_the_missing_hour_are_refused(self):
        for reading in (
            datetime(2025, 3, 9, 2, 0),
            datetime(2025, 3, 9, 2, 0, 1),
            datetime(2025, 3, 9, 2, 30),
            datetime(2025, 3, 9, 2, 59, 59),
            datetime(2026, 3, 8, 2, 30),
        ):
            with self.subTest(reading=reading):
                self.refuses(GapError, raw_to_utc, reading)
                self.refuses(GapError, raw_to_utc, reading, 1)
        self.assertEqual(
            self.to_utc(datetime(2025, 3, 9, 1, 59, 59)), datetime(2025, 3, 9, 6, 59, 59)
        )
        self.assertEqual(self.to_utc(datetime(2025, 3, 9, 3, 0)), datetime(2025, 3, 9, 7, 0))
        self.assertEqual(self.to_utc(datetime(2026, 3, 8, 3, 0)), datetime(2026, 3, 8, 7, 0))


class SpanTest(KernelCase):
    def test_moments_before_the_table_is_refused(self):
        self.refuses(CoverageError, raw_to_local, datetime(2024, 12, 31, 23, 0))
        self.refuses(CoverageError, EASTERN.offset_at, datetime(2024, 12, 31, 23, 0))
        self.refuses(CoverageError, raw_to_utc, datetime(2024, 12, 31, 18, 59, 59))
        self.refuses(CoverageError, raw_to_utc, datetime(1995, 6, 1, 12, 0))
        self.assertEqual(self.to_local(datetime(2025, 1, 1, 0, 0)), datetime(2024, 12, 31, 19, 0))
        self.assertEqual(self.to_utc(datetime(2024, 12, 31, 19, 0)), datetime(2025, 1, 1, 0, 0))
        self.assertEqual(self.to_utc(datetime(2024, 12, 31, 20, 0)), datetime(2025, 1, 1, 1, 0))


class TableDefinitionTest(KernelCase):
    def test_malformed_tables_are_refused(self):
        first = (datetime(2025, 1, 1, 0, 0), -5 * HOUR, "EST")
        second = (datetime(2025, 3, 9, 7, 0), -4 * HOUR, "EDT")
        for table in (
            42,
            (),
            [second, first],
            [first, (datetime(2025, 1, 1, 0, 0), -4 * HOUR, "X")],
            [first, "2025-03-09"],
            [(datetime(2025, 1, 1, 0, 0), 15 * HOUR, "X")],
            [(datetime(2025, 1, 1, 0, 0), -13 * HOUR, "X")],
            [(datetime(2025, 1, 1, 0, 0), 90, "X")],
            [(datetime(2025, 1, 1, 0, 0), timedelta(seconds=30), "X")],
            [(datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc), -5 * HOUR, "EST")],
            [("2025-01-01", -5 * HOUR, "EST")],
        ):
            with self.subTest(table=table):
                self.refuses(TableError, OffsetTable, table)


class ChangeoverListTest(KernelCase):
    def test_changeovers_and_the_year_boundary(self):
        self.assertEqual(
            EASTERN.transitions(),
            [
                (datetime(2025, 3, 9, 7, 0), -5 * HOUR, -4 * HOUR),
                (datetime(2025, 11, 2, 6, 0), -4 * HOUR, -5 * HOUR),
                (datetime(2026, 3, 8, 7, 0), -5 * HOUR, -4 * HOUR),
                (datetime(2026, 11, 1, 6, 0), -4 * HOUR, -5 * HOUR),
            ],
        )
        roster = OffsetTable(
            (
                (datetime(2025, 1, 1, 0, 0), 2 * HOUR, "CET"),
                (datetime(2025, 6, 1, 0, 0), 2 * HOUR, "CEST"),
                (datetime(2025, 10, 1, 0, 0), 1 * HOUR, "CET"),
            )
        )
        self.assertEqual(
            roster.transitions(), [(datetime(2025, 10, 1, 0, 0), 2 * HOUR, 1 * HOUR)]
        )
        self.assertEqual(roster.name_at(datetime(2025, 7, 1, 0, 0)), "CEST")
        self.assertEqual(roster.name_at(datetime(2025, 11, 1, 0, 0)), "CET")
        self.assertEqual(self.to_local(datetime(2026, 1, 1, 4, 30)), datetime(2025, 12, 31, 23, 30))
        self.assertEqual(
            self.to_local(datetime(2026, 1, 1, 4, 30, 15)), datetime(2025, 12, 31, 23, 30, 15)
        )
        self.assertEqual(self.to_utc(datetime(2025, 12, 31, 23, 30)), datetime(2026, 1, 1, 4, 30))
        self.assertEqual(self.to_utc(datetime(2026, 1, 1, 0, 30)), datetime(2026, 1, 1, 5, 30))
        self.assertEqual(self.to_local(datetime(2026, 1, 1, 5, 30)), datetime(2026, 1, 1, 0, 30))
        self.assertEqual(self.to_utc(datetime(2027, 1, 1, 0, 0)), datetime(2027, 1, 1, 5, 0))


class UniqueReadingTest(KernelCase):
    def test_fold_is_ignored_when_the_reading_happens_once(self):
        for reading in (
            datetime(2025, 6, 15, 9, 0),
            datetime(2025, 12, 25, 0, 0),
            datetime(2026, 7, 4, 23, 30),
            datetime(2026, 10, 31, 23, 0),
        ):
            with self.subTest(reading=reading):
                instant = self.to_utc(reading)
                self.assertEqual(self.to_utc(reading, 1), instant)
                self.assertEqual(self.to_local(instant), reading)
                self.refuses(TimeZoneError, raw_to_utc, reading, 2)


if __name__ == "__main__":
    unittest.main()
