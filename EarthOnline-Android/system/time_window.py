"""Default player-facing half-hour tracking window.

Database slot indexes remain 0..47 for backward compatibility.  The visible
recording rows start at 08:00 and include the 23:30 row, whose interval ends at
24:00.  Records from 00:00 through 08:00 are not shown or required.  Existing
older records outside this window remain preserved in SQLite.
"""

TRACKING_START_SLOT = 16  # 08:00
TRACKING_END_SLOT = 48    # exclusive; includes slot 47 (23:30-24:00)
TRACKING_SLOTS = tuple(range(TRACKING_START_SLOT, TRACKING_END_SLOT))
TRACKING_SLOT_COUNT = len(TRACKING_SLOTS)
