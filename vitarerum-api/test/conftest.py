"""Test-session composition root.

A test process opens database sessions and builds schemas from
``Base.metadata``, so it needs every ORM mapper registered — exactly like a
migration or a scheduled job. Without this, a test file that happens not to
import a given context fails to resolve foreign keys into it, and the suite
passes or fails depending on which files ran first.
"""

import app.orm_registry  # noqa: F401  (registers every mapper)
