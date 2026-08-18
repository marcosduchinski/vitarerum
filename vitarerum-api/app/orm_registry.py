"""Imports every ORM model module so the mappers are fully registered.

SQLAlchemy resolves a foreign key only once the table it points at exists in the
metadata, and several contexts reference each other's tables. The API happens to
register everything because ``app.main`` imports every router; anything else
that opens a session — a migration, a scheduled job — has to say so explicitly.

Importing this module is a composition-root concern. A bounded context must not
import it: that would pull in the contexts it is forbidden to depend on.
"""

from app.ai.museum_narrative.infrastructure import models as museum_narrative_models
from app.ai.museum_question_triage.infrastructure import (
    models as museum_question_triage_models,
)
from app.ai.prompts.infrastructure import models as ai_prompts_models
from app.cidoc_crm.in_situ_visit_mapping.infrastructure import (
    models as in_situ_visit_models,
)
from app.collection_object_index.infrastructure import (
    models as collection_object_index_models,
)
from app.document_templates.infrastructure import models as document_templates_models
from app.external_publications.infrastructure import (
    models as external_publications_models,
)
from app.identity.infrastructure import models as identity_models
from app.museum_questions.infrastructure import models as museum_questions_models
from app.notifications.infrastructure import models as notifications_models
from app.public_submission.infrastructure import models as public_submission_models
from app.reference_numbers.infrastructure import models as reference_numbers_models
from app.reports.in_situ_visit.infrastructure import (
    models as in_situ_visit_report_models,
)
from app.scientific_return.infrastructure import models as scientific_return_models
from app.use_of_collections.infrastructure import models as use_of_collections_models

__all__ = [
    "ai_prompts_models",
    "collection_object_index_models",
    "document_templates_models",
    "external_publications_models",
    "identity_models",
    "in_situ_visit_models",
    "in_situ_visit_report_models",
    "museum_narrative_models",
    "museum_question_triage_models",
    "museum_questions_models",
    "notifications_models",
    "public_submission_models",
    "reference_numbers_models",
    "scientific_return_models",
    "use_of_collections_models",
]
