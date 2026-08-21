"""Passline QC thresholds — single source of truth.

All numeric limits used by the rule engine, corruption engine, and tests
are defined here and imported everywhere else.  Never define a threshold
in two places.
"""

# Reading speed
CPS_VIOLATION: float = 20.0        # CPS > this  → ERROR  (cps_exceeded)
CPS_WARNING_LOW: float = 17.0      # CPS in [this, CPS_VIOLATION] → WARNING (cps_warning)

# Line length
LINE_CHAR_MAX: int = 42            # chars > this → ERROR (line_too_long)

# Lines per cue
MAX_LINES_PER_CUE: int = 2         # lines > this → WARNING (three_line_cue)

# Display duration
MIN_DURATION_MS: int = 1_000       # ms < this → ERROR (sub_one_second)
