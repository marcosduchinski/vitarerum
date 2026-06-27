"""Route aggregator for the Use of Collections inbound adapter.

The endpoints live in proposal_routes / project_routes / journal_routes
(HEXAGONAL_UP.md Step 7); importing them registers the handlers on the two
routers defined in common.py. main.py keeps importing the routers from here.
"""

from app.use_of_collections.presentation import (  # noqa: F401
    journal_routes,
    project_routes,
    proposal_routes,
)
from app.use_of_collections.presentation.common import (
    projects_router,
    proposals_router,
)

__all__ = ["projects_router", "proposals_router"]
