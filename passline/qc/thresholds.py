"""Passline QC thresholds — single source of truth.

All numeric limits used by the rule engine, corruption engine, and tests
are defined here and imported everywhere else.  Never define a threshold
in two places.
"""

# Reading speed
CPS_VIOLATION: float = 20.0        # CPS > this  → ERROR  (cps_exceeded)
CPS_WARNING_LOW: float = 17.0      # CPS in [this, CPS_VIOLATION] → WARNING (cps_warning)

# Reading speed (CJK)
CPS_VIOLATION_CJK: float = 9.0
CPS_WARNING_LOW_CJK: float = 7.0

# Line length
LINE_CHAR_MAX: int = 42            # chars > this → ERROR (line_too_long)
LINE_CHAR_MAX_OVERRIDES: dict[str, int] = {
    "ru": 39,
}
LINE_CHAR_MAX_CJK: int = 16        # full-width chars > this → ERROR

# Lines per cue
MAX_LINES_PER_CUE: int = 2         # lines > this → WARNING (three_line_cue)

# Display duration
MIN_DURATION_MS: int = 1_000       # ms < this → ERROR (sub_one_second)
