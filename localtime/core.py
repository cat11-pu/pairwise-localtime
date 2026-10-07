"""A fixed offset table kernel for UTC and wall clock conversion.

The kernel carries no timezone data of its own.  The caller supplies an
offset table -- an ordered list of fixed offset segments -- and the kernel
only does arithmetic on naive datetimes.  It never reads the system clock,
the disk or the network, and it never invents an offset the table does not
state.

A segment is a ``(start, offset, name)`` triple:

* ``start`` is a naive datetime read as UTC, the instant the offset becomes
  effective at,
* ``offset`` is a :class:`datetime.timedelta` east of UTC, and
* ``name`` is an opaque label such as ``"EST"``.

A segment stands from its own start until the next segment's start, so
consecutive starts have to be strictly ascending and the last segment stands
forever.  The instants a table answers for are ``[first start, infinity)``;
an earlier instant raises :class:`CoverageError`.

A *UTC instant* is a naive datetime meant as UTC, a *local reading* is a
naive datetime meant as the wall clock of the zone.  :func:`utc_to_local`
and :func:`local_to_utc` move between the two and are exact inverses, down
to the seconds and microseconds of an instant, with two deliberate
exceptions around a changeover:

* a reading in the hour a fall back changeover runs through twice resolves
  to the earlier instant, or to the later one when ``fold=1``, and
* a reading in the hour a spring forward changeover jumps over does not
  happen at all and is refused with :class:`GapError`.

Segments are read and stored as they are given; the kernel keeps them in a
tuple and looks one up by scanning the starts in order.
"""

from datetime import datetime, timedelta

__all__ = [
    "TimeZoneError",
    "TableError",
    "CoverageError",
    "GapError",
    "Segment",
    "OffsetTable",
    "utc_to_local",
    "local_to_utc",
]

#: Offsets a segment may carry, west and east of UTC.
MIN_OFFSET = timedelta(hours=-12)
MAX_OFFSET = timedelta(hours=14)


class TimeZoneError(ValueError):
    """Base class of every complaint this kernel makes."""


class TableError(TimeZoneError):
    """Raised when an offset table cannot be built."""


class CoverageError(TimeZoneError):
    """Raised for an instant the offset table says nothing about."""


class GapError(TimeZoneError):
    """Raised for a local reading that never happens."""


class Segment:
    """One fixed offset segment: where it starts, its offset and its name."""

    __slots__ = ("start", "offset", "name")

    def __init__(self, start, offset, name=""):
        self.start = start
        self.offset = offset
        self.name = name

    def __repr__(self):
        return "Segment(%r, %r, %r)" % (self.start, self.offset, self.name)


def _checked_start(value):
    """Read one segment start, which has to be a naive datetime."""
    if not isinstance(value, datetime):
        raise TableError("segment start must be a datetime, got %r" % (value,))
    if value.tzinfo is not None:
        raise TableError("segment start must be naive, got %r" % (value,))
    return value


def _checked_offset(value):
    """Read one segment offset, a whole number of minutes east of UTC."""
    if not isinstance(value, timedelta):
        raise TableError("segment offset must be a timedelta, got %r" % (value,))
    if value < MIN_OFFSET or value > MAX_OFFSET:
        raise TableError(
            "segment offset %r is outside %r..%r" % (value, MIN_OFFSET, MAX_OFFSET)
        )
    if value.microseconds or value.seconds % 60:
        raise TableError("segment offset %r is finer than a minute" % (value,))
    return value


class OffsetTable:
    """An ordered list of fixed offset segments.

    The list is fixed once the table is built: segments are validated,
    stored in the given order and never touched again.
    """

    __slots__ = ("_segments", "_offsets")

    def __init__(self, segments):
        try:
            items = list(segments)
        except TypeError:
            raise TableError("an offset table needs a list of segments, got %r" % (segments,))
        parsed = []
        for item in items:
            try:
                start, offset, name = item
            except (TypeError, ValueError):
                raise TableError("segment %r is not a (start, offset, name) triple" % (item,))
            parsed.append(Segment(_checked_start(start), _checked_offset(offset), str(name)))
        if not parsed:
            raise TableError("an offset table needs at least one segment")
        for earlier, later in zip(parsed, parsed[1:]):
            if later.start <= earlier.start:
                raise TableError("segment at %r is not after %r" % (later.start, earlier.start))
        self._segments = tuple(parsed)
        self._offsets = tuple(sorted({segment.offset for segment in parsed}))

    def __len__(self):
        return len(self._segments)

    def __iter__(self):
        return iter(self._segments)

    def __repr__(self):
        return "OffsetTable(%r)" % (self._segments,)

    @property
    def segments(self):
        """Every segment of the table, in force order."""
        return self._segments

    @property
    def offsets(self):
        """Every distinct offset of the table, ascending."""
        return self._offsets

    @property
    def first_start(self):
        """The earliest instant the table covers."""
        return self._segments[0].start

    def segment_index_at(self, instant):
        """Index of the segment that is in force at a UTC instant."""
        index = 0
        for position in range(1, len(self._segments)):
            if instant >= self._segments[position].start:
                index = position
            else:
                break
        return index

    def segment_at(self, instant):
        """The segment in force at a UTC instant."""
        if instant < self.first_start:
            raise CoverageError("instant %r is before the table" % (instant,))
        return self._segments[self.segment_index_at(instant)]

    def offset_at(self, instant):
        """The offset in force at a UTC instant."""
        return self.segment_at(instant).offset

    def name_at(self, instant):
        """The name of the segment in force at a UTC instant."""
        return self.segment_at(instant).name

    def local_floor(self):
        """The earliest local reading the table is able to show."""
        return self.first_start + self._segments[0].offset

    def instants_for_local(self, local):
        """Every covered UTC instant whose local reading is *local*.

        Ascending.  An hour that runs twice gives two instants, an hour that
        never runs gives none.
        """
        found = []
        for offset in self._offsets:
            instant = local - offset
            try:
                current = self.offset_at(instant)
            except CoverageError:
                continue
            if current == offset:
                found.append(instant)
        found.sort()
        return found

    def transitions(self):
        """The changeovers of the table, as ``(instant, before, after)``.

        A pair of neighbouring segments that share an offset is not a
        changeover and is left out.
        """
        result = []
        for earlier, later in zip(self._segments, self._segments[1:]):
            if earlier.offset == later.offset:
                continue
            result.append((later.start, earlier.offset, later.offset))
        return result


def _checked_moment(value, what):
    """Read a naive datetime argument."""
    if not isinstance(value, datetime):
        raise TimeZoneError("%s must be a datetime, got %r" % (what, value))
    if value.tzinfo is not None:
        raise TimeZoneError("%s must be naive, got %r" % (what, value))
    return value


def utc_to_local(table, instant):
    """The local reading the table shows at a UTC instant."""
    _checked_moment(instant, "instant")
    segment = table.segment_at(instant)
    return instant + segment.offset


def local_to_utc(table, local, fold=0):
    """The UTC instant a local reading stands for.

    ``fold`` picks the side of a reading that happens twice: ``0`` the
    earlier instant, ``1`` the later one.
    """
    _checked_moment(local, "local reading")
    if fold not in (0, 1):
        raise TimeZoneError("fold must be 0 or 1, got %r" % (fold,))
    if local < table.local_floor():
        raise CoverageError("local reading %r is before the table" % (local,))
    candidates = table.instants_for_local(local)
    if not candidates:
        raise GapError("local reading %r never happens" % (local,))
    if fold:
        return candidates[-1]
    return candidates[0]
