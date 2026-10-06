# localtime

A fixed offset table kernel for UTC and wall clock conversion, written with the
Python standard library only. There is nothing to install, no timezone database
is involved and the kernel never reads the system clock, the disk or the
network. The caller brings the offset table; the kernel does the arithmetic on
naive datetimes.

## What is inside

* `localtime/core.py` - the offset table, the segment lookup and the two
  conversion functions.
* `tests/test_core.py` - the acceptance tests for the kernel.

## Public interface

```python
from datetime import datetime, timedelta
from localtime import OffsetTable, GapError, local_to_utc, utc_to_local

eastern = OffsetTable([
    (datetime(2025, 1, 1, 0, 0), -5 * timedelta(hours=1), "EST"),
    (datetime(2025, 3, 9, 7, 0), -4 * timedelta(hours=1), "EDT"),
    (datetime(2025, 11, 2, 6, 0), -5 * timedelta(hours=1), "EST"),
])

utc_to_local(eastern, datetime(2025, 7, 15, 12, 0))    # datetime(2025, 7, 15, 8, 0)
local_to_utc(eastern, datetime(2025, 11, 2, 1, 30))    # the earlier instant
local_to_utc(eastern, datetime(2025, 11, 2, 1, 30), 1) # the later instant
eastern.offset_at(datetime(2025, 7, 15, 12, 0))        # timedelta(hours=-4)
eastern.name_at(datetime(2025, 7, 15, 12, 0))          # "EDT"
eastern.transitions()                                  # [(instant, before, after), ...]
```

## The model

* A table entry is a `(start, offset, name)` triple. `start` is a naive
  datetime read as UTC, `offset` is the offset east of UTC in whole minutes and
  `name` is an opaque label.
* A segment stands from its own start until the next segment's start; the last
  segment stands forever. Consecutive starts have to be strictly ascending, so
  a repeated or a backwards start is a `TableError`.
* Starts have to be naive datetimes and offsets have to be whole minutes
  between -12:00 and +14:00; anything else is a `TableError` too.
* A *UTC instant* is a naive datetime meant as UTC and a *local reading* is a
  naive datetime meant as the zone's wall clock. `utc_to_local` adds the offset
  in force, `local_to_utc` removes it, and the two are exact inverses down to
  the seconds and microseconds of an instant.

Around a changeover a reading is not always single valued:

* a reading in the hour a fall back changeover runs through twice has two
  instants; `fold=0` (the default) returns the earlier one and `fold=1` the
  later one, and any other `fold` is an error;
* a reading in the hour a spring forward changeover jumps over has none and
  raises `GapError`;
* a reading only happens once when it is not in such an hour, whatever `fold`
  says.

The instants a table answers for are `[first start, infinity)`. An instant
earlier than that, and a local reading earlier than the table's earliest
readable wall clock time, raise `CoverageError` instead of being stretched to
the nearest segment.

## Running the tests

From the project root:

    python3 -m unittest discover -s tests -v

All of the tests have to pass.
