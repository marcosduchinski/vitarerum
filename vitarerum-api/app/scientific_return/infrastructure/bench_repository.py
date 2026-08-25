"""SQLAlchemy adapter for the scientific-return local-corpus test bench."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from time import monotonic
from uuid import uuid4

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.scientific_return.application.full_agentic_ports import FullAgenticReasoner
from app.scientific_return.domain.bench_models import (
    TestAttemptStatus,
    TestBatchStatus,
    TestInventoryEvidenceStatus,
    TestItemStatus,
    TestSourceKind,
    TestSourceStatus,
    TestSubject,
    derive_batch_status,
)
from app.scientific_return.domain.enums import FullAgenticInvestigationStatus
from app.scientific_return.domain.full_agentic_models import AgenticBudget
from app.scientific_return.infrastructure.bench_agentic_runtime import (
    BENCH_SCORE_VERSION,
    BenchAgenticOutcome,
    LocalCorpusDocument,
    evidence_score,
    execute_bench_agentic,
)
from app.scientific_return.infrastructure.full_agentic_repository import (
    SqlAlchemyFullAgenticRepository,
)
from app.scientific_return.infrastructure.models import (
    ScientificReturnTestBatchRecord,
    ScientificReturnTestBatchSourceRecord,
    ScientificReturnTestCandidateRecord,
    ScientificReturnTestItemRecord,
    ScientificReturnTestSearchAttemptRecord,
    ScientificReturnTestSourceRecord,
    ScientificReturnTestSourceRevisionRecord,
)
from app.shared.field_encryption import FieldEncryptor


class BenchNotFound(Exception):
    pass


class BenchConflict(Exception):
    pass


class BenchInvalid(Exception):
    pass


def _now() -> datetime:
    return datetime.now(UTC)


def _hash(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def _canonical_content(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n").strip()


class _RevisionContentCache:
    """Small process-local plaintext cache; never persisted or logged."""

    def __init__(
        self, max_bytes: int = 64 * 1024 * 1024, ttl_seconds: int = 600
    ) -> None:
        self._max_bytes = max_bytes
        self._ttl_seconds = ttl_seconds
        self._entries: OrderedDict[str, tuple[float, str]] = OrderedDict()
        self._bytes = 0

    def get(self, key: str) -> str | None:
        entry = self._entries.pop(key, None)
        if entry is None:
            return None
        expires_at, value = entry
        if expires_at <= monotonic():
            self._bytes -= len(value.encode("utf-8"))
            return None
        self._entries[key] = entry
        return value

    def put(self, key: str, value: str) -> None:
        size = len(value.encode("utf-8"))
        if size > self._max_bytes:
            return
        old = self._entries.pop(key, None)
        if old:
            self._bytes -= len(old[1].encode("utf-8"))
        self._entries[key] = (monotonic() + self._ttl_seconds, value)
        self._bytes += size
        while self._bytes > self._max_bytes and self._entries:
            _, (_, evicted) = self._entries.popitem(last=False)
            self._bytes -= len(evicted.encode("utf-8"))


_CONTENT_CACHE = _RevisionContentCache()


class SqlAlchemyBenchRepository:
    def __init__(
        self,
        session: AsyncSession,
        encryptor: FieldEncryptor,
        *,
        reasoner: FullAgenticReasoner | None = None,
        budget: AgenticBudget | None = None,
    ) -> None:
        self.session = session
        self.encryptor = encryptor
        self.reasoner = reasoner
        self.budget = budget or AgenticBudget(
            max_iterations=4,
            max_queries=12,
            max_results=40,
            max_candidates=5,
            max_llm_calls=20,
        )

    async def create_source(
        self,
        *,
        institution_id: str,
        actor_id: str,
        name: str,
        kind: TestSourceKind,
        content: str,
        locator: str | None,
        authors: Sequence[str],
    ) -> ScientificReturnTestSourceRecord:
        content = _canonical_content(content)
        content_hash = _hash(content)
        duplicate = await self.session.scalar(
            select(ScientificReturnTestSourceRecord).where(
                ScientificReturnTestSourceRecord.institution_id == institution_id,
                ScientificReturnTestSourceRecord.content_hash == content_hash,
            )
        )
        if duplicate:
            raise BenchConflict("An identical source already exists")
        now = _now()
        source_id, revision_id = str(uuid4()), str(uuid4())
        source = ScientificReturnTestSourceRecord(
            id=source_id,
            institution_id=institution_id,
            name=name,
            kind=kind,
            status=TestSourceStatus.ACTIVE,
            current_revision=1,
            content_hash=content_hash,
            created_by=actor_id,
            created_at=now,
            updated_at=now,
        )
        revision = ScientificReturnTestSourceRevisionRecord(
            id=revision_id,
            source_id=source_id,
            revision=1,
            locator=locator,
            authors_payload=self.encryptor.encrypt_json(
                list(authors), f"sr_test_source_revision:{revision_id}:authors"
            ),
            content_payload=self.encryptor.encrypt_required_text(
                content, f"sr_test_source_revision:{revision_id}:content"
            ),
            content_hash=content_hash,
            created_by=actor_id,
            created_at=now,
        )
        self.session.add_all((source, revision))
        await self.session.flush()
        return source

    async def list_sources(
        self, institution_id: str, status: TestSourceStatus | None
    ) -> list[dict[str, object]]:
        stmt = select(ScientificReturnTestSourceRecord).where(
            ScientificReturnTestSourceRecord.institution_id == institution_id
        )
        if status:
            stmt = stmt.where(ScientificReturnTestSourceRecord.status == status)
        records = (
            await self.session.scalars(
                stmt.order_by(ScientificReturnTestSourceRecord.name)
            )
        ).all()
        return [self._source_summary(record) for record in records]

    async def source_detail(
        self, source_id: str, institution_id: str
    ) -> dict[str, object]:
        source = await self._source(source_id, institution_id)
        revisions = (
            await self.session.scalars(
                select(ScientificReturnTestSourceRevisionRecord)
                .where(ScientificReturnTestSourceRevisionRecord.source_id == source.id)
                .order_by(ScientificReturnTestSourceRevisionRecord.revision.desc())
            )
        ).all()
        result = self._source_summary(source)
        result["revisions"] = [self._revision_view(record) for record in revisions]
        return result

    async def replace_source(
        self,
        *,
        source_id: str,
        institution_id: str,
        actor_id: str,
        name: str,
        kind: TestSourceKind,
        content: str,
        locator: str | None,
        authors: Sequence[str],
    ) -> ScientificReturnTestSourceRecord:
        source = await self._source(source_id, institution_id)
        content = _canonical_content(content)
        content_hash = _hash(content)
        if content_hash == source.content_hash:
            raise BenchConflict(
                "The replacement content is identical to the current revision"
            )
        revision_number = source.current_revision + 1
        revision_id = str(uuid4())
        self.session.add(
            ScientificReturnTestSourceRevisionRecord(
                id=revision_id,
                source_id=source.id,
                revision=revision_number,
                locator=locator,
                authors_payload=self.encryptor.encrypt_json(
                    list(authors), f"sr_test_source_revision:{revision_id}:authors"
                ),
                content_payload=self.encryptor.encrypt_required_text(
                    content, f"sr_test_source_revision:{revision_id}:content"
                ),
                content_hash=content_hash,
                created_by=actor_id,
                created_at=_now(),
            )
        )
        source.name = name
        source.kind = kind
        source.current_revision = revision_number
        source.content_hash = content_hash
        source.updated_at = _now()
        await self.session.flush()
        return source

    async def set_source_status(
        self, source_id: str, institution_id: str, status: TestSourceStatus
    ) -> ScientificReturnTestSourceRecord:
        source = await self._source(source_id, institution_id)
        source.status = status
        source.updated_at = _now()
        await self.session.flush()
        return source

    async def create_batch(
        self,
        institution_id: str,
        actor_id: str,
        name: str | None,
        description: str | None,
    ) -> ScientificReturnTestBatchRecord:
        record = ScientificReturnTestBatchRecord(
            id=str(uuid4()),
            institution_id=institution_id,
            name=name,
            description=description,
            status=TestBatchStatus.DRAFT,
            idempotency_key=None,
            cancellation_requested=False,
            created_by=actor_id,
            created_at=_now(),
            started_at=None,
            completed_at=None,
            version=0,
        )
        self.session.add(record)
        await self.session.flush()
        return record

    async def list_batches(self, institution_id: str) -> list[dict[str, object]]:
        records = (
            await self.session.scalars(
                select(ScientificReturnTestBatchRecord)
                .where(ScientificReturnTestBatchRecord.institution_id == institution_id)
                .order_by(ScientificReturnTestBatchRecord.created_at.desc())
            )
        ).all()
        return [await self.batch_view(record) for record in records]

    async def add_items(
        self, batch_id: str, institution_id: str, subjects: Sequence[TestSubject]
    ) -> list[ScientificReturnTestItemRecord]:
        batch = await self._batch(batch_id, institution_id)
        self._draft(batch)
        current = await self.session.scalar(
            select(func.count())
            .select_from(ScientificReturnTestItemRecord)
            .where(ScientificReturnTestItemRecord.batch_id == batch.id)
        )
        items: list[ScientificReturnTestItemRecord] = []
        for offset, subject in enumerate(subjects, start=int(current or 0) + 1):
            item_id = str(uuid4())
            joined = "\0".join(
                (subject.author, subject.object_name, subject.inventory_number)
            )
            item = ScientificReturnTestItemRecord(
                id=item_id,
                batch_id=batch.id,
                ordinal=offset,
                author_payload=self.encryptor.encrypt_required_text(
                    subject.author, f"sr_test_item:{item_id}:author"
                ),
                object_name_payload=self.encryptor.encrypt_required_text(
                    subject.object_name, f"sr_test_item:{item_id}:object"
                ),
                inventory_number_payload=self.encryptor.encrypt_required_text(
                    subject.inventory_number, f"sr_test_item:{item_id}:inventory"
                ),
                subject_hash=_hash(joined),
                status=TestItemStatus.PENDING,
                attempt_number=1,
                lease_owner=None,
                lease_expires_at=None,
                heartbeat_at=None,
                error_code=None,
                error_message=None,
                started_at=None,
                completed_at=None,
                version=0,
            )
            self.session.add(item)
            items.append(item)
        await self.session.flush()
        return items

    async def remove_item(
        self, batch_id: str, item_id: str, institution_id: str
    ) -> None:
        batch = await self._batch(batch_id, institution_id)
        self._draft(batch)
        item = await self.session.scalar(
            select(ScientificReturnTestItemRecord.id).where(
                ScientificReturnTestItemRecord.id == item_id,
                ScientificReturnTestItemRecord.batch_id == batch.id,
            )
        )
        if item is None:
            raise BenchNotFound("Test item not found")
        await self.session.execute(
            delete(ScientificReturnTestItemRecord).where(
                ScientificReturnTestItemRecord.id == item_id,
                ScientificReturnTestItemRecord.batch_id == batch.id,
            )
        )

    async def select_sources(
        self, batch_id: str, institution_id: str, source_ids: Sequence[str]
    ) -> None:
        batch = await self._batch(batch_id, institution_id)
        self._draft(batch)
        await self.session.execute(
            delete(ScientificReturnTestBatchSourceRecord).where(
                ScientificReturnTestBatchSourceRecord.batch_id == batch.id
            )
        )
        for source_id in dict.fromkeys(source_ids):
            source = await self._source(source_id, institution_id)
            if source.status is not TestSourceStatus.ACTIVE:
                raise BenchInvalid("Only active sources can be selected")
            revision = await self.session.scalar(
                select(ScientificReturnTestSourceRevisionRecord).where(
                    ScientificReturnTestSourceRevisionRecord.source_id == source.id,
                    ScientificReturnTestSourceRevisionRecord.revision
                    == source.current_revision,
                )
            )
            if revision is None:
                raise BenchInvalid("Source revision is unavailable")
            self.session.add(
                ScientificReturnTestBatchSourceRecord(
                    id=str(uuid4()),
                    batch_id=batch.id,
                    source_id=source.id,
                    revision_id=revision.id,
                    source_name=source.name,
                    source_revision=revision.revision,
                    locator=revision.locator,
                    content_hash=revision.content_hash,
                )
            )
        await self.session.flush()

    async def start_batch(
        self, batch_id: str, institution_id: str, idempotency_key: str
    ) -> tuple[dict[str, object], list[str]]:
        bound = await self.session.scalar(
            select(ScientificReturnTestBatchRecord).where(
                ScientificReturnTestBatchRecord.idempotency_key == idempotency_key
            )
        )
        if bound:
            if bound.id != batch_id:
                raise BenchConflict(
                    "Idempotency-Key is already bound to another test batch"
                )
            return await self.batch_view(bound), []
        batch = await self._batch(batch_id, institution_id)
        self._draft(batch)
        items = (
            await self.session.scalars(
                select(ScientificReturnTestItemRecord)
                .where(ScientificReturnTestItemRecord.batch_id == batch.id)
                .order_by(ScientificReturnTestItemRecord.ordinal)
            )
        ).all()
        snapshots = (
            await self.session.scalars(
                select(ScientificReturnTestBatchSourceRecord).where(
                    ScientificReturnTestBatchSourceRecord.batch_id == batch.id
                )
            )
        ).all()
        if not items:
            raise BenchInvalid("TEST_BATCH_EMPTY")
        if not snapshots:
            raise BenchInvalid("TEST_SOURCE_SELECTION_EMPTY")
        batch.idempotency_key = idempotency_key
        batch.status = TestBatchStatus.QUEUED
        batch.started_at = _now()
        batch.version += 1
        await self.session.flush()
        return await self.batch_view(batch), [item.id for item in items]

    async def snapshot_character_count(self, batch_id: str, institution_id: str) -> int:
        await self._batch(batch_id, institution_id)
        revision_ids = list(
            await self.session.scalars(
                select(ScientificReturnTestBatchSourceRecord.revision_id).where(
                    ScientificReturnTestBatchSourceRecord.batch_id == batch_id
                )
            )
        )
        total = 0
        for revision_id in revision_ids:
            revision = await self.session.get(
                ScientificReturnTestSourceRevisionRecord, revision_id
            )
            if revision is None:
                raise BenchInvalid("TEST_SOURCE_REVISION_INVALID")
            content = _CONTENT_CACHE.get(revision.content_hash)
            if content is None:
                content = (
                    self.encryptor.decrypt_text(
                        revision.content_payload,
                        f"sr_test_source_revision:{revision.id}:content",
                    )
                    or ""
                )
                _CONTENT_CACHE.put(revision.content_hash, content)
            total += len(content)
        return total

    async def cancel_batch(
        self, batch_id: str, institution_id: str
    ) -> dict[str, object]:
        batch = await self._batch(batch_id, institution_id)
        if batch.status.terminal:
            return await self.batch_view(batch)
        batch.cancellation_requested = True
        await self.session.execute(
            update(ScientificReturnTestItemRecord)
            .where(
                ScientificReturnTestItemRecord.batch_id == batch.id,
                ScientificReturnTestItemRecord.status == TestItemStatus.PENDING,
            )
            .values(status=TestItemStatus.CANCELLED, completed_at=_now())
        )
        await self._recalculate(batch)
        return await self.batch_view(batch)

    async def retry_item(
        self, batch_id: str, item_id: str, institution_id: str
    ) -> dict[str, object]:
        batch = await self._batch(batch_id, institution_id)
        if batch.status not in {
            TestBatchStatus.FAILED,
            TestBatchStatus.COMPLETED_WITH_ERRORS,
        }:
            raise BenchConflict("Only a failed batch item can be retried")
        item = await self.session.scalar(
            select(ScientificReturnTestItemRecord).where(
                ScientificReturnTestItemRecord.id == item_id,
                ScientificReturnTestItemRecord.batch_id == batch.id,
            )
        )
        if item is None:
            raise BenchNotFound("Test item not found")
        if item.status is not TestItemStatus.ERROR:
            raise BenchConflict("Only an item in ERROR can be retried")
        item.status = TestItemStatus.PENDING
        item.attempt_number += 1
        item.error_code = item.error_message = None
        item.completed_at = None
        item.version += 1
        batch.status = TestBatchStatus.QUEUED
        batch.completed_at = None
        batch.version += 1
        await self.session.flush()
        return self._item_view(item)

    async def claim_and_execute(self, item_id: str, worker_id: str) -> bool:
        item = await self.session.scalar(
            select(ScientificReturnTestItemRecord)
            .where(
                ScientificReturnTestItemRecord.id == item_id,
                or_(
                    ScientificReturnTestItemRecord.status == TestItemStatus.PENDING,
                    (
                        (
                            ScientificReturnTestItemRecord.status
                            == TestItemStatus.RUNNING
                        )
                        & (ScientificReturnTestItemRecord.lease_expires_at < _now())
                    ),
                ),
            )
            .with_for_update(skip_locked=True)
        )
        if item is None:
            return False
        batch = await self.session.get(ScientificReturnTestBatchRecord, item.batch_id)
        if batch is None or batch.cancellation_requested:
            item.status = TestItemStatus.CANCELLED
            item.completed_at = _now()
            if batch:
                await self._recalculate(batch)
            await self.session.flush()
            return False
        item.status = TestItemStatus.RUNNING
        item.lease_owner = worker_id
        item.heartbeat_at = _now()
        item.lease_expires_at = _now() + timedelta(minutes=5)
        item.started_at = _now()
        item.version += 1
        batch.status = TestBatchStatus.RUNNING
        await self.session.flush()
        item_id_value = item.id
        try:
            await self._execute_claimed(item, batch)
        except Exception:
            # A database-level failure leaves the transaction aborted, so the
            # failure has to be recorded from a clean one. Writing the ERROR
            # state onto the dead transaction would raise a second exception
            # and take the sibling items of the batch down with it.
            await self.session.rollback()
            await self._fail_item(
                item_id_value,
                "TEST_ITEM_EXECUTION_FAILED",
                "The test item could not be processed",
            )
            return True
        return True

    async def _fail_item(self, item_id: str, code: str, message: str) -> None:
        """Record a terminal item failure in a transaction of its own."""
        item = await self.session.get(ScientificReturnTestItemRecord, item_id)
        if item is None:
            return
        item.status = TestItemStatus.ERROR
        item.error_code = code
        item.error_message = message
        item.completed_at = _now()
        item.lease_owner = None
        item.lease_expires_at = None
        item.version += 1
        batch = await self.session.get(ScientificReturnTestBatchRecord, item.batch_id)
        if batch is not None:
            await self._recalculate(batch)
        await self.session.flush()

    async def _execute_claimed(
        self,
        item: ScientificReturnTestItemRecord,
        batch: ScientificReturnTestBatchRecord,
    ) -> None:
        subject = self._subject(item)
        snapshots = (
            await self.session.scalars(
                select(ScientificReturnTestBatchSourceRecord)
                .where(ScientificReturnTestBatchSourceRecord.batch_id == batch.id)
                .order_by(ScientificReturnTestBatchSourceRecord.source_name)
            )
        ).all()
        documents: list[LocalCorpusDocument] = []
        for snapshot in snapshots:
            revision = await self.session.get(
                ScientificReturnTestSourceRevisionRecord, snapshot.revision_id
            )
            if revision is None:
                continue
            content = _CONTENT_CACHE.get(revision.content_hash)
            if content is None:
                content = (
                    self.encryptor.decrypt_text(
                        revision.content_payload,
                        f"sr_test_source_revision:{revision.id}:content",
                    )
                    or ""
                )
                _CONTENT_CACHE.put(revision.content_hash, content)
            authors = (
                self.encryptor.decrypt_json(
                    revision.authors_payload,
                    f"sr_test_source_revision:{revision.id}:authors",
                )
                or []
            )
            documents.append(
                LocalCorpusDocument(
                    source_id=snapshot.source_id,
                    revision_id=revision.id,
                    name=snapshot.source_name,
                    revision=snapshot.source_revision,
                    locator=revision.locator,
                    authors=tuple(str(value) for value in authors),
                    content=content,
                    content_hash=revision.content_hash,
                )
            )
        knowledge = await SqlAlchemyFullAgenticRepository(
            self.session, self.encryptor
        ).list_knowledge(active_only=True, limit=120)
        scoped_knowledge = tuple(
            entry
            for entry in knowledge
            if entry.institution_id in {None, batch.institution_id}
        )
        outcome = await execute_bench_agentic(
            item_id=item.id,
            attempt_number=item.attempt_number,
            created_by=batch.created_by,
            subject=subject,
            documents=tuple(documents),
            reasoner=self.reasoner,
            budget=self.budget,
            worker_id=item.lease_owner or "scientific-return-test-worker",
            knowledge=scoped_knowledge,
        )
        if outcome.investigation.status is not FullAgenticInvestigationStatus.COMPLETED:
            raise RuntimeError(
                outcome.investigation.failure_reason
                or "Autonomous search did not complete"
            )
        await self._persist_agentic_outcome(item, tuple(documents), outcome)
        item.status = TestItemStatus.COMPLETED
        item.completed_at = _now()
        item.lease_owner = None
        item.lease_expires_at = None
        item.heartbeat_at = _now()
        item.version += 1
        await self._recalculate(batch)
        await self.session.flush()

    async def _persist_agentic_outcome(
        self,
        item: ScientificReturnTestItemRecord,
        documents: tuple[LocalCorpusDocument, ...],
        outcome: BenchAgenticOutcome,
    ) -> None:
        documents_by_revision = {
            document.revision_id: document for document in documents
        }
        linked_analysis_ids = {
            str(event.payload.get("candidateId")): str(event.payload.get("analysisId"))
            for event in outcome.operations.events
            if event.kind.value == "CANDIDATE_LINKED"
        }
        attempts: dict[tuple[str, str], ScientificReturnTestSearchAttemptRecord] = {}
        for tool in sorted(
            outcome.operations.tools.values(), key=lambda value: value.started_at
        ):
            query = str(tool.invocation.get("query", ""))
            result = tool.result or {}
            raw_records = result.get("records", [])
            returned = (
                {
                    str(record.get("source_record_id"))
                    for record in raw_records
                    if isinstance(record, dict)
                }
                if isinstance(raw_records, list)
                else set()
            )
            for document in documents:
                attempt = await self._upsert_attempt(
                    item=item,
                    document=document,
                    query=query,
                    result_count=int(document.revision_id in returned),
                )
                attempts[(query, document.revision_id)] = attempt
        await self.session.flush()
        for link in sorted(outcome.operations.links, key=lambda value: value.rank):
            candidate = outcome.scientific.candidates.get(str(link.candidate_id))
            analysis = outcome.scientific.analyses.get(
                linked_analysis_ids.get(str(link.candidate_id), "")
            )
            if candidate is None or analysis is None:
                continue
            candidate_document = documents_by_revision.get(candidate.source_record_id)
            query = str(analysis.input_payload.get("query", ""))
            candidate_attempt = attempts.get((query, candidate.source_record_id))
            if candidate_document is None or candidate_attempt is None:
                continue
            candidate_attempt.model = analysis.model
            candidate_attempt.prompt_version_id = analysis.prompt_version_id
            candidate_attempt.prompt_version = analysis.prompt_version
            passages = analysis.input_payload.get("passages", [])
            evidence = (
                str(passages[0]) if isinstance(passages, list) and passages else None
            )
            start = candidate_document.content.find(evidence) if evidence else -1
            candidate_id = str(uuid4())
            self.session.add(
                ScientificReturnTestCandidateRecord(
                    id=candidate_id,
                    attempt_id=candidate_attempt.id,
                    rank=link.rank,
                    score=evidence_score(analysis),
                    score_version=BENCH_SCORE_VERSION,
                    discovery_basis=str(
                        analysis.input_payload.get("discoveryBasis", "UNKNOWN")
                    ),
                    inventory_evidence_status=TestInventoryEvidenceStatus(
                        str(
                            analysis.input_payload.get(
                                "inventoryEvidenceStatus", "UNAVAILABLE"
                            )
                        )
                    ),
                    evidence_payload=self.encryptor.encrypt_text(
                        evidence, f"sr_test_candidate:{candidate_id}:evidence"
                    ),
                    evidence_start=start if start >= 0 else None,
                    evidence_end=(start + len(evidence))
                    if evidence and start >= 0
                    else None,
                    source_field="indexed_text" if evidence else None,
                )
            )

    async def _upsert_attempt(
        self,
        *,
        item: ScientificReturnTestItemRecord,
        document: LocalCorpusDocument,
        query: str,
        result_count: int,
    ) -> ScientificReturnTestSearchAttemptRecord:
        query_hash = _hash(query.casefold())
        attempt = await self.session.scalar(
            select(ScientificReturnTestSearchAttemptRecord).where(
                ScientificReturnTestSearchAttemptRecord.item_id == item.id,
                ScientificReturnTestSearchAttemptRecord.item_attempt_number
                == item.attempt_number,
                ScientificReturnTestSearchAttemptRecord.source_revision_id
                == document.revision_id,
                ScientificReturnTestSearchAttemptRecord.query_hash == query_hash,
            )
        )
        if attempt is None:
            attempt_id = str(uuid4())
            attempt = ScientificReturnTestSearchAttemptRecord(
                id=attempt_id,
                item_id=item.id,
                item_attempt_number=item.attempt_number,
                source_revision_id=document.revision_id,
                query_payload=self.encryptor.encrypt_required_text(
                    query, f"sr_test_attempt:{attempt_id}:query"
                ),
                query_hash=query_hash,
                status=TestAttemptStatus.COMPLETED,
                result_count=result_count,
                model=None,
                prompt_version_id=None,
                prompt_version=None,
                started_at=_now(),
                completed_at=_now(),
            )
            self.session.add(attempt)
            return attempt
        await self.session.execute(
            delete(ScientificReturnTestCandidateRecord).where(
                ScientificReturnTestCandidateRecord.attempt_id == attempt.id
            )
        )
        attempt.status = TestAttemptStatus.COMPLETED
        attempt.result_count = result_count
        attempt.model = None
        attempt.prompt_version_id = None
        attempt.prompt_version = None
        attempt.started_at = _now()
        attempt.completed_at = _now()
        return attempt

    async def candidates(
        self, batch_id: str, institution_id: str
    ) -> list[dict[str, object]]:
        await self._batch(batch_id, institution_id)
        stmt = (
            select(
                ScientificReturnTestCandidateRecord,
                ScientificReturnTestSearchAttemptRecord,
                ScientificReturnTestItemRecord,
                ScientificReturnTestSourceRevisionRecord,
                ScientificReturnTestSourceRecord,
            )
            .join(
                ScientificReturnTestSearchAttemptRecord,
                ScientificReturnTestSearchAttemptRecord.id
                == ScientificReturnTestCandidateRecord.attempt_id,
            )
            .join(
                ScientificReturnTestItemRecord,
                ScientificReturnTestItemRecord.id
                == ScientificReturnTestSearchAttemptRecord.item_id,
            )
            .join(
                ScientificReturnTestSourceRevisionRecord,
                ScientificReturnTestSourceRevisionRecord.id
                == ScientificReturnTestSearchAttemptRecord.source_revision_id,
            )
            .join(
                ScientificReturnTestSourceRecord,
                ScientificReturnTestSourceRecord.id
                == ScientificReturnTestSourceRevisionRecord.source_id,
            )
            .where(
                ScientificReturnTestItemRecord.batch_id == batch_id,
                ScientificReturnTestSearchAttemptRecord.status
                == TestAttemptStatus.COMPLETED,
                ScientificReturnTestSearchAttemptRecord.item_attempt_number
                == ScientificReturnTestItemRecord.attempt_number,
            )
            .order_by(
                ScientificReturnTestItemRecord.ordinal,
                ScientificReturnTestCandidateRecord.rank,
            )
        )
        rows = (await self.session.execute(stmt)).all()
        return [self._candidate_view(*row) for row in rows]

    async def batch_detail(
        self, batch_id: str, institution_id: str
    ) -> dict[str, object]:
        return await self.batch_view(await self._batch(batch_id, institution_id))

    async def batch_view(
        self, batch: ScientificReturnTestBatchRecord
    ) -> dict[str, object]:
        items = (
            await self.session.scalars(
                select(ScientificReturnTestItemRecord)
                .where(ScientificReturnTestItemRecord.batch_id == batch.id)
                .order_by(ScientificReturnTestItemRecord.ordinal)
            )
        ).all()
        sources = (
            await self.session.scalars(
                select(ScientificReturnTestBatchSourceRecord)
                .where(ScientificReturnTestBatchSourceRecord.batch_id == batch.id)
                .order_by(ScientificReturnTestBatchSourceRecord.source_name)
            )
        ).all()
        counts = {
            status.value.lower(): sum(item.status is status for item in items)
            for status in TestItemStatus
        }
        return {
            "id": batch.id,
            "name": batch.name,
            "description": batch.description,
            "status": batch.status.value,
            "createdAt": batch.created_at,
            "startedAt": batch.started_at,
            "completedAt": batch.completed_at,
            "progress": {
                "total": len(items),
                **counts,
                "percentage": round(
                    100
                    * (counts["completed"] + counts["error"] + counts["cancelled"])
                    / len(items)
                )
                if items
                else 0,
            },
            "sourceIds": [source.source_id for source in sources],
            "sources": [
                {
                    "sourceId": source.source_id,
                    "revisionId": source.revision_id,
                    "name": source.source_name,
                    "revision": source.source_revision,
                    "locator": source.locator,
                    "contentHash": source.content_hash,
                }
                for source in sources
            ],
            "items": [self._item_view(item) for item in items],
        }

    def _source_summary(
        self, source: ScientificReturnTestSourceRecord
    ) -> dict[str, object]:
        return {
            "id": source.id,
            "name": source.name,
            "kind": source.kind.value,
            "status": source.status.value,
            "currentRevision": source.current_revision,
            "contentHash": source.content_hash,
            "createdAt": source.created_at,
            "updatedAt": source.updated_at,
        }

    def _revision_view(
        self, revision: ScientificReturnTestSourceRevisionRecord
    ) -> dict[str, object]:
        content = (
            self.encryptor.decrypt_text(
                revision.content_payload,
                f"sr_test_source_revision:{revision.id}:content",
            )
            or ""
        )
        authors = (
            self.encryptor.decrypt_json(
                revision.authors_payload,
                f"sr_test_source_revision:{revision.id}:authors",
            )
            or []
        )
        return {
            "id": revision.id,
            "revision": revision.revision,
            "locator": revision.locator,
            "authors": authors,
            "content": content,
            "contentHash": revision.content_hash,
            "createdAt": revision.created_at,
        }

    def _subject(self, item: ScientificReturnTestItemRecord) -> TestSubject:
        return TestSubject(
            author=self.encryptor.decrypt_text(
                item.author_payload, f"sr_test_item:{item.id}:author"
            )
            or "",
            object_name=self.encryptor.decrypt_text(
                item.object_name_payload, f"sr_test_item:{item.id}:object"
            )
            or "",
            inventory_number=self.encryptor.decrypt_text(
                item.inventory_number_payload, f"sr_test_item:{item.id}:inventory"
            )
            or "",
        )

    def _item_view(self, item: ScientificReturnTestItemRecord) -> dict[str, object]:
        subject = self._subject(item)
        return {
            "id": item.id,
            "ordinal": item.ordinal,
            "author": subject.author,
            "objectName": subject.object_name,
            "inventoryNumber": subject.inventory_number,
            "status": item.status.value,
            "attemptNumber": item.attempt_number,
            "errorCode": item.error_code,
            "errorMessage": item.error_message,
            "startedAt": item.started_at,
            "completedAt": item.completed_at,
        }

    def _candidate_view(
        self,
        candidate: ScientificReturnTestCandidateRecord,
        attempt: ScientificReturnTestSearchAttemptRecord,
        item: ScientificReturnTestItemRecord,
        revision: ScientificReturnTestSourceRevisionRecord,
        source: ScientificReturnTestSourceRecord,
    ) -> dict[str, object]:
        subject = self._subject(item)
        return {
            "id": candidate.id,
            "itemId": item.id,
            "attemptNumber": attempt.item_attempt_number,
            "author": subject.author,
            "objectName": subject.object_name,
            "inventoryNumber": subject.inventory_number,
            "rank": candidate.rank,
            "score": candidate.score,
            "scoreVersion": candidate.score_version,
            "sourceId": source.id,
            "sourceName": source.name,
            "sourceRevision": revision.revision,
            "sourceLocator": revision.locator,
            "query": self.encryptor.decrypt_text(
                attempt.query_payload, f"sr_test_attempt:{attempt.id}:query"
            )
            or "",
            "discoveryBasis": candidate.discovery_basis,
            "inventoryEvidenceStatus": candidate.inventory_evidence_status.value,
            "evidence": self.encryptor.decrypt_text(
                candidate.evidence_payload, f"sr_test_candidate:{candidate.id}:evidence"
            ),
        }

    async def _source(
        self, source_id: str, institution_id: str
    ) -> ScientificReturnTestSourceRecord:
        record = await self.session.scalar(
            select(ScientificReturnTestSourceRecord).where(
                ScientificReturnTestSourceRecord.id == source_id,
                ScientificReturnTestSourceRecord.institution_id == institution_id,
            )
        )
        if record is None:
            raise BenchNotFound("Test source not found")
        return record

    async def _batch(
        self, batch_id: str, institution_id: str
    ) -> ScientificReturnTestBatchRecord:
        record = await self.session.scalar(
            select(ScientificReturnTestBatchRecord).where(
                ScientificReturnTestBatchRecord.id == batch_id,
                ScientificReturnTestBatchRecord.institution_id == institution_id,
            )
        )
        if record is None:
            raise BenchNotFound("Test batch not found")
        return record

    @staticmethod
    def _draft(batch: ScientificReturnTestBatchRecord) -> None:
        if batch.status is not TestBatchStatus.DRAFT:
            raise BenchConflict("TEST_BATCH_NOT_DRAFT")

    async def _recalculate(self, batch: ScientificReturnTestBatchRecord) -> None:
        statuses = list(
            await self.session.scalars(
                select(ScientificReturnTestItemRecord.status).where(
                    ScientificReturnTestItemRecord.batch_id == batch.id
                )
            )
        )
        batch.status = derive_batch_status(
            statuses, cancellation_requested=batch.cancellation_requested
        )
        if batch.status.terminal:
            batch.completed_at = _now()
        batch.version += 1
