from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.ai.museum_question_triage.domain.models import (
    TriageVerdict,
    UseCategory,
    UseCategoryScore,
)


class CatalogueSearchPolicy(StrEnum):
    NEVER = "NEVER"
    ALWAYS = "ALWAYS"
    WHEN_OBJECT_MENTIONED = "WHEN_OBJECT_MENTIONED"


@dataclass(frozen=True, slots=True)
class UseCategoryDefinition:
    category: UseCategory
    is_collection_use: bool
    catalogue_search_policy: CatalogueSearchPolicy


USE_CATEGORY_DEFINITIONS: dict[UseCategory, UseCategoryDefinition] = {
    UseCategory.EXHIBITION: UseCategoryDefinition(
        category=UseCategory.EXHIBITION,
        is_collection_use=False,
        catalogue_search_policy=CatalogueSearchPolicy.NEVER,
    ),
    UseCategory.PUBLISHING_IMAGES: UseCategoryDefinition(
        category=UseCategory.PUBLISHING_IMAGES,
        is_collection_use=True,
        catalogue_search_policy=CatalogueSearchPolicy.WHEN_OBJECT_MENTIONED,
    ),
    UseCategory.LEARNING_EVENTS: UseCategoryDefinition(
        category=UseCategory.LEARNING_EVENTS,
        is_collection_use=False,
        catalogue_search_policy=CatalogueSearchPolicy.NEVER,
    ),
    UseCategory.ANSWERING_ENQUIRIES: UseCategoryDefinition(
        category=UseCategory.ANSWERING_ENQUIRIES,
        is_collection_use=True,
        catalogue_search_policy=CatalogueSearchPolicy.WHEN_OBJECT_MENTIONED,
    ),
    UseCategory.RESEARCH_PROJECTS: UseCategoryDefinition(
        category=UseCategory.RESEARCH_PROJECTS,
        is_collection_use=True,
        catalogue_search_policy=CatalogueSearchPolicy.ALWAYS,
    ),
    UseCategory.OPERATING_MACHINERY: UseCategoryDefinition(
        category=UseCategory.OPERATING_MACHINERY,
        is_collection_use=True,
        catalogue_search_policy=CatalogueSearchPolicy.WHEN_OBJECT_MENTIONED,
    ),
    UseCategory.PLAYING_INSTRUMENTS: UseCategoryDefinition(
        category=UseCategory.PLAYING_INSTRUMENTS,
        is_collection_use=True,
        catalogue_search_policy=CatalogueSearchPolicy.WHEN_OBJECT_MENTIONED,
    ),
    UseCategory.FILMING: UseCategoryDefinition(
        category=UseCategory.FILMING,
        is_collection_use=False,
        catalogue_search_policy=CatalogueSearchPolicy.NEVER,
    ),
    UseCategory.INSPIRING_NEW_WORK: UseCategoryDefinition(
        category=UseCategory.INSPIRING_NEW_WORK,
        is_collection_use=True,
        catalogue_search_policy=CatalogueSearchPolicy.WHEN_OBJECT_MENTIONED,
    ),
}


def derived_scope_from_categories(
    assigned_categories: list[UseCategoryScore],
) -> TriageVerdict:
    if any(
        USE_CATEGORY_DEFINITIONS[score.category].is_collection_use
        for score in assigned_categories
    ):
        return TriageVerdict.IN_SCOPE
    return TriageVerdict.OUT_OF_SCOPE


def should_search_catalogue_for_categories(
    assigned_categories: list[UseCategoryScore],
    *,
    mentioned_object_count: int,
) -> bool:
    has_mentioned_objects = mentioned_object_count > 0
    for score in assigned_categories:
        policy = USE_CATEGORY_DEFINITIONS[score.category].catalogue_search_policy
        if policy is CatalogueSearchPolicy.ALWAYS:
            return True
        if (
            policy is CatalogueSearchPolicy.WHEN_OBJECT_MENTIONED
            and has_mentioned_objects
        ):
            return True
    return False
