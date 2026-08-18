"""Composition-root entry point for the scientific-return CLI.

``app.scientific_return.presentation.commands`` implements the commands, but it
cannot register the ORM on its own: its candidate table has a foreign key into
``use_of_collections``, and the context is forbidden from importing that context
directly. The API never noticed because ``app.main`` imports every router, and
that happens to register every mapper. A job process imports nothing of the
sort, so registration belongs here, at the composition root, before the command
opens its first session.

    python -m app.jobs.scientific_return run-due --limit 25
"""

from __future__ import annotations

import app.orm_registry  # noqa: F401  (registers every mapper)
from app.scientific_return.presentation.commands import main

if __name__ == "__main__":
    main()
