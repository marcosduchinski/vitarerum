"""Composition root for the Use of Collections inbound adapter.

All wiring of concrete outbound adapters (SQLAlchemy repositories, file
storage, Identity's PermissionReader) happens here; the route modules depend
only on ports and these FastAPI dependency factories.
"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.identity.public import (
    PermissionReader,
    get_permission_reader,
    get_requester_provisioner,
)
from app.use_of_collections.application.ports import (
    AmendmentInvitationPort,
    CollectionUseProjectRepository,
    ConversationRepository,
    ExternalRequesterProvisioner,
    FileStoragePort,
    ObjectAccessLogRepository,
    ObjectOccurrenceLogRepository,
    ProposalRepository,
    PublicationLogRepository,
)
from app.use_of_collections.application.queries import (
    GetProjectDetail,
    GetProposalDetail,
    ListProjects,
    ListProposals,
)
from app.use_of_collections.infrastructure.amendment_invitation import (
    LoggingAmendmentInvitation,
)
from app.use_of_collections.infrastructure.external_requester import (
    IdentityExternalRequesterProvisioner,
)
from app.use_of_collections.infrastructure.file_storage import LocalDiskFileStorage
from app.use_of_collections.infrastructure.repositories import (
    SqlAlchemyCollectionUseProjectRepository,
    SqlAlchemyConversationRepository,
    SqlAlchemyObjectAccessLogRepository,
    SqlAlchemyObjectOccurrenceLogRepository,
    SqlAlchemyProposalRepository,
    SqlAlchemyPublicationLogRepository,
)

from app.config import settings  # isort: skip

DBSession = Annotated[AsyncSession, Depends(get_async_session)]


def get_project_repo(session: DBSession) -> CollectionUseProjectRepository:
    return SqlAlchemyCollectionUseProjectRepository(session)


def get_proposal_repo(session: DBSession) -> ProposalRepository:
    return SqlAlchemyProposalRepository(session)


def get_conversation_repo(session: DBSession) -> ConversationRepository:
    return SqlAlchemyConversationRepository(session)


def get_access_log_repo(session: DBSession) -> ObjectAccessLogRepository:
    return SqlAlchemyObjectAccessLogRepository(session)


def get_occurrence_log_repo(session: DBSession) -> ObjectOccurrenceLogRepository:
    return SqlAlchemyObjectOccurrenceLogRepository(session)


def get_publication_log_repo(session: DBSession) -> PublicationLogRepository:
    return SqlAlchemyPublicationLogRepository(session)


def get_file_storage() -> FileStoragePort:
    return LocalDiskFileStorage(settings.data_dir)


def get_amendment_invitation() -> AmendmentInvitationPort:
    """Default (logging) invitation adapter.

    Overridden at the composition root (``app.main``) with the real
    token-minting / e-mailing adapter from the public-submission context."""
    return LoggingAmendmentInvitation()


def get_reader(session: DBSession) -> PermissionReader:
    return get_permission_reader(session)


def get_external_requester_provisioner(
    session: DBSession,
) -> ExternalRequesterProvisioner:
    return IdentityExternalRequesterProvisioner(get_requester_provisioner(session))


ProjectRepo = Annotated[CollectionUseProjectRepository, Depends(get_project_repo)]
ProposalRepo = Annotated[ProposalRepository, Depends(get_proposal_repo)]
ConvRepo = Annotated[ConversationRepository, Depends(get_conversation_repo)]
AccessLogRepo = Annotated[ObjectAccessLogRepository, Depends(get_access_log_repo)]
OccurrenceLogRepo = Annotated[
    ObjectOccurrenceLogRepository, Depends(get_occurrence_log_repo)
]
PublicationLogRepo = Annotated[
    PublicationLogRepository, Depends(get_publication_log_repo)
]
FileStorage = Annotated[FileStoragePort, Depends(get_file_storage)]
AmendmentInvitation = Annotated[
    AmendmentInvitationPort, Depends(get_amendment_invitation)
]
PermReader = Annotated[PermissionReader, Depends(get_reader)]
RequesterProvisioner = Annotated[
    ExternalRequesterProvisioner, Depends(get_external_requester_provisioner)
]


def get_list_proposals_query(
    proposal_repo: ProposalRepo, reader: PermReader
) -> ListProposals:
    return ListProposals(proposal_repo, reader)


def get_proposal_detail_query(
    proposal_repo: ProposalRepo,
    project_repo: ProjectRepo,
    conversation_repo: ConvRepo,
    reader: PermReader,
) -> GetProposalDetail:
    return GetProposalDetail(proposal_repo, project_repo, conversation_repo, reader)


def get_list_projects_query(
    project_repo: ProjectRepo, proposal_repo: ProposalRepo, reader: PermReader
) -> ListProjects:
    return ListProjects(project_repo, proposal_repo, reader)


def get_project_detail_query(
    project_repo: ProjectRepo, proposal_repo: ProposalRepo, reader: PermReader
) -> GetProjectDetail:
    return GetProjectDetail(project_repo, proposal_repo, reader)


ListProposalsQuery = Annotated[ListProposals, Depends(get_list_proposals_query)]
ProposalDetailQuery = Annotated[GetProposalDetail, Depends(get_proposal_detail_query)]
ListProjectsQuery = Annotated[ListProjects, Depends(get_list_projects_query)]
ProjectDetailQuery = Annotated[GetProjectDetail, Depends(get_project_detail_query)]
