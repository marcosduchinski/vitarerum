from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.external_publications.application.use_cases import (
    CreateExternalPublication,
    GetExternalPublishedJsonLd,
    ListExternalPublicationAccesses,
    ListExternalPublications,
    ListPublishableResources,
    ResolveExternalPublication,
    RevokeExternalPublication,
)
from app.external_publications.infrastructure.acls import (
    ProjectPublicationReader,
    ProposalPublicationReader,
    ReportsPublicationAcl,
    UseOfCollectionsPublicationAcl,
)
from app.external_publications.infrastructure.clock import SystemClock
from app.external_publications.infrastructure.repositories import (
    SqlAlchemyExternalPublicationAccessRepository,
    SqlAlchemyExternalPublicationRepository,
)
from app.external_publications.infrastructure.tokens import (
    OpaqueTokenGenerator,
    Sha256TokenHasher,
)

DBSession = Annotated[AsyncSession, Depends(get_async_session)]


def get_repository(
    session: DBSession,
) -> SqlAlchemyExternalPublicationRepository:
    return SqlAlchemyExternalPublicationRepository(session)


def get_access_repository(
    session: DBSession,
) -> SqlAlchemyExternalPublicationAccessRepository:
    return SqlAlchemyExternalPublicationAccessRepository(session)


def get_use_of_collections_acl(
    session: DBSession,
) -> UseOfCollectionsPublicationAcl:
    return UseOfCollectionsPublicationAcl(session)


def get_proposal_reader(
    acl: Annotated[UseOfCollectionsPublicationAcl, Depends(get_use_of_collections_acl)],
) -> ProposalPublicationReader:
    return ProposalPublicationReader(acl)


def get_project_reader(
    acl: Annotated[UseOfCollectionsPublicationAcl, Depends(get_use_of_collections_acl)],
) -> ProjectPublicationReader:
    return ProjectPublicationReader(acl)


def get_report_reader(session: DBSession) -> ReportsPublicationAcl:
    return ReportsPublicationAcl(session)


def get_clock() -> SystemClock:
    return SystemClock()


def get_token_generator() -> OpaqueTokenGenerator:
    return OpaqueTokenGenerator()


def get_token_hasher() -> Sha256TokenHasher:
    return Sha256TokenHasher()


Repository = Annotated[
    SqlAlchemyExternalPublicationRepository,
    Depends(get_repository),
]
AccessRepository = Annotated[
    SqlAlchemyExternalPublicationAccessRepository,
    Depends(get_access_repository),
]
ProposalReader = Annotated[ProposalPublicationReader, Depends(get_proposal_reader)]
ProjectReader = Annotated[ProjectPublicationReader, Depends(get_project_reader)]
ReportReader = Annotated[ReportsPublicationAcl, Depends(get_report_reader)]
PublicationClock = Annotated[SystemClock, Depends(get_clock)]
TokenGeneratorDep = Annotated[OpaqueTokenGenerator, Depends(get_token_generator)]
TokenHasherDep = Annotated[Sha256TokenHasher, Depends(get_token_hasher)]


def get_create_use_case(
    repository: Repository,
    proposal_reader: ProposalReader,
    project_reader: ProjectReader,
    report_reader: ReportReader,
    token_generator: TokenGeneratorDep,
    token_hasher: TokenHasherDep,
    clock: PublicationClock,
) -> CreateExternalPublication:
    return CreateExternalPublication(
        repository,
        proposal_reader,
        project_reader,
        report_reader,
        token_generator,
        token_hasher,
        clock,
    )


def get_list_use_case(repository: Repository) -> ListExternalPublications:
    return ListExternalPublications(repository)


def get_list_accesses_use_case(
    repository: Repository,
    access_repository: AccessRepository,
) -> ListExternalPublicationAccesses:
    return ListExternalPublicationAccesses(repository, access_repository)


def get_list_publishable_use_case(
    proposal_reader: ProposalReader,
    project_reader: ProjectReader,
    report_reader: ReportReader,
) -> ListPublishableResources:
    return ListPublishableResources(proposal_reader, project_reader, report_reader)


def get_revoke_use_case(
    repository: Repository,
    clock: PublicationClock,
) -> RevokeExternalPublication:
    return RevokeExternalPublication(repository, clock)


def get_resolve_use_case(
    repository: Repository,
    access_repository: AccessRepository,
    proposal_reader: ProposalReader,
    project_reader: ProjectReader,
    report_reader: ReportReader,
    token_hasher: TokenHasherDep,
    clock: PublicationClock,
) -> ResolveExternalPublication:
    return ResolveExternalPublication(
        repository,
        access_repository,
        proposal_reader,
        project_reader,
        report_reader,
        token_hasher,
        clock,
    )


def get_json_ld_use_case(
    resolver: Annotated[ResolveExternalPublication, Depends(get_resolve_use_case)],
    report_reader: ReportReader,
) -> GetExternalPublishedJsonLd:
    return GetExternalPublishedJsonLd(resolver, report_reader)


CreateUseCase = Annotated[CreateExternalPublication, Depends(get_create_use_case)]
ListUseCase = Annotated[ListExternalPublications, Depends(get_list_use_case)]
ListAccessesUseCase = Annotated[
    ListExternalPublicationAccesses,
    Depends(get_list_accesses_use_case),
]
ListPublishableUseCase = Annotated[
    ListPublishableResources,
    Depends(get_list_publishable_use_case),
]
RevokeUseCase = Annotated[RevokeExternalPublication, Depends(get_revoke_use_case)]
ResolveUseCase = Annotated[ResolveExternalPublication, Depends(get_resolve_use_case)]
JsonLdUseCase = Annotated[GetExternalPublishedJsonLd, Depends(get_json_ld_use_case)]
