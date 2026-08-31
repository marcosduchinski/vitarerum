import { inject, Injectable } from '@angular/core';
import { IDENTITY_SERVICE } from '@core/auth/identity.service';
import { PermissionPrincipal } from '@core/auth/models/permission.model';
import { Page, PageQuery } from '@shared/models/page.model';
import { Observable, of, throwError } from 'rxjs';

import {
  AddRequestedObjectsRequest,
  ApproveProposalRequest,
  AssignProposalRequest,
  ForwardProposalRequest,
  ProposalAssignmentResult,
  ProposalCancellationResult,
  ProposalCommandResult,
  ProposalDecisionResult,
  ProposalReasonRequest,
  RequestDocumentCorrectionsRequest,
  ReferProposalToDirectionRequest,
  ReturnProposalToStaffRequest,
  UpdateProposalRequest,
} from '../models/proposal-actions.model';
import {
  Conversation,
  CreateProposalRequest,
  CreateProposalResponse,
  Document,
  DocumentCorrectionItem,
  Message,
  MessageAttachment,
  ProposalDetail,
  ProposalDocumentsResponse,
  ProposalEventsPage,
  ProposalEvent,
  ProposalListQuery,
  ProposalSummary,
  RequestedObject,
  SendMessageRequest,
  UpdateProposalResult,
} from '../models/proposal.model';
import { makePageFrom, MOCK_SEED, MOCK_USERS, MockProjectState, P } from './mock-data';

@Injectable()
export class ProposalApiServiceMock {
  private readonly seed = inject(MOCK_SEED, { optional: true });
  private readonly identity = inject(IDENTITY_SERVICE);
  private readonly projectState = inject(MockProjectState);
  private readonly proposals = new Map<string, ProposalDetail>(
    (this.seed?.proposals ?? []).map((p) => [p.id, structuredClone(p)]),
  );
  private readonly events = new Map<string, ProposalEvent[]>(
    Object.entries(this.seed?.proposalEvents ?? {}).map(([k, v]) => [k, structuredClone(v)]),
  );
  private readonly messages = new Map<string, Message[]>(
    Object.entries(this.seed?.messages ?? {}).map(([k, v]) => [k, structuredClone(v)]),
  );
  private nextId = 100;

  createProposal(request: CreateProposalRequest): Observable<CreateProposalResponse> {
    const id = `prop-${this.nextId}`;
    this.nextId++;
    const now = new Date().toISOString();
    const seq = this.proposals.size + 1;
    const proposalRef = `VRP-${now.slice(0, 10).replace(/-/g, '')}-${String(seq).padStart(4, '0')}`;
    const convId = `conv-${id}`;
    const title = request.title?.trim() || request.initialMessageSubject?.trim() || proposalRef;
    const purpose = request.purpose?.trim() || request.initialMessageBody?.trim() || '';
    const intendedUse = request.intendedUse ?? 'OTHER';
    const submittedDocuments: Document[] = (request.documents ?? []).map((file, index) => ({
      id: `doc-${id}-${index + 1}`,
      type: 'REQUESTER_ATTACHMENT',
      fileName: file.name,
      submittedAt: now,
      submittedBy: this.currentPrincipal(),
    }));

    const proposal: ProposalDetail = {
      id,
      referenceNumber: proposalRef,
      title,
      status: 'SUBMITTED',
      submissionChannel: 'AUTHENTICATED',
      type: intendedUse,
      intendedUse,
      beginDate: request.beginDate ?? undefined,
      endDate: request.endDate ?? undefined,
      requestedBy: this.currentPrincipal(),
      assignedTo: null,
      submittedAt: now,
      conversationId: convId,
      documents: submittedDocuments,
      requestedObjects: [],
      correctionItems: [],
    };

    this.proposals.set(id, proposal);
    this.events.set(id, [
      { occurredAt: now, type: 'SUBMITTED', triggeredBy: this.currentPrincipal(), note: null },
    ]);
    // Business Rule 01: a proposal opens with one message. The conversation is
    // seeded from the request's initialMessage* fields, falling back to
    // recipient → collections@…, subject → title, body → purpose.
    this.messages.set(convId, [
      {
        id: `msg-${this.nextId++}`,
        sentAt: now,
        sender: this.currentPrincipal().user.email,
        recipient: request.initialMessageRecipient ?? 'collections@vitarerum.example.com',
        subject: request.initialMessageSubject ?? title,
        body: request.initialMessageBody ?? purpose,
      },
    ]);

    return of({
      proposal: {
        id: proposal.id,
        referenceNumber: proposal.referenceNumber,
        title: proposal.title,
        status: proposal.status,
        submissionChannel: proposal.submissionChannel,
        type: proposal.type,
        intendedUse: proposal.intendedUse,
        beginDate: proposal.beginDate,
        endDate: proposal.endDate,
        requestedBy: proposal.requestedBy,
        assignedTo: proposal.assignedTo,
        submittedAt: proposal.submittedAt,
      },
      conversationId: convId,
    });
  }

  listProposals(query: ProposalListQuery = {}): Observable<Page<ProposalSummary>> {
    let items = [...this.proposals.values()];

    const statuses = typeof query.status === 'string' ? [query.status] : (query.status ?? []);
    if (statuses.length) items = items.filter((p) => statuses.includes(p.status));
    if (query.type) items = items.filter((p) => p.type === query.type);
    if (query.requestedBy)
      items = items.filter((p) => p.requestedBy.permissionId === query.requestedBy);
    if (query.assignedTo)
      items = items.filter((p) => p.assignedTo?.permissionId === query.assignedTo);
    if (query.search) {
      const q = query.search.toLowerCase();
      items = items.filter(
        (p) =>
          (p.title ?? '').toLowerCase().includes(q) || p.referenceNumber.toLowerCase().includes(q),
      );
    }

    const summaries: ProposalSummary[] = items.map((p) => ({
      id: p.id,
      referenceNumber: p.referenceNumber,
      title: p.title,
      status: p.status,
      submissionChannel: p.submissionChannel,
      type: p.type,
      beginDate: p.beginDate,
      endDate: p.endDate,
      requestedBy: p.requestedBy,
      assignedTo: p.assignedTo,
      collectionUseProject: p.collectionUseProject,
      submittedAt: p.submittedAt,
    }));

    return of(makePageFrom(summaries, query));
  }

  getProposal(proposalId: string): Observable<ProposalDetail> {
    const proposal = this.proposals.get(proposalId);
    if (!proposal) return throwError(() => ({ status: 404, error: 'NOT_FOUND' }));
    return of(proposal);
  }

  updateProposal(
    proposalId: string,
    request: UpdateProposalRequest,
  ): Observable<UpdateProposalResult> {
    const proposal = this.proposals.get(proposalId);
    if (!proposal) {
      return throwError(() => ({
        status: 404,
        error: 'PROPOSAL_NOT_FOUND',
        message: `No proposal found with id ${proposalId}`,
      }));
    }
    if (!this.identity.isStaff()) {
      return throwError(() => ({
        status: 403,
        error: 'INSUFFICIENT_GROUP',
        message: 'Only staff members can perform this action',
      }));
    }
    if (proposal.status !== 'SUBMITTED' && proposal.status !== 'PENDING') {
      return throwError(() => ({
        status: 409,
        error: 'INVALID_TRANSITION',
        message: 'Cannot edit a proposal that is already decided or cancelled',
      }));
    }

    const title = request.title === undefined ? proposal.title : request.title;
    const beginDate =
      request.beginDate === undefined ? (proposal.beginDate ?? null) : request.beginDate;
    const endDate = request.endDate === undefined ? (proposal.endDate ?? null) : request.endDate;
    const intendedUse = request.intendedUse ?? proposal.intendedUse;

    if (beginDate && endDate && endDate < beginDate) {
      return throwError(() => ({
        status: 422,
        error: 'INVALID_DATE_RANGE',
        message: 'endDate must be after beginDate',
      }));
    }

    const updated = {
      ...proposal,
      title,
      beginDate,
      endDate,
      intendedUse,
      type: request.intendedUse ?? proposal.type,
    };

    // ProposalDetail still models rollout-era nullable fields as optional. The
    // mock deliberately stores explicit nulls so PATCH behavior matches the
    // backend contract; the UI nullability migration is handled separately.
    this.proposals.set(proposalId, updated as ProposalDetail);

    return of({
      id: proposalId,
      referenceNumber: proposal.referenceNumber,
      title,
      status: proposal.status,
      beginDate,
      endDate,
      lastEvent: this.events.get(proposalId)?.at(-1) ?? null,
    });
  }

  addRequestedObjects(
    proposalId: string,
    request: AddRequestedObjectsRequest,
  ): Observable<ProposalDetail> {
    const proposal = this.proposals.get(proposalId);
    if (!proposal) return throwError(() => ({ status: 404, error: 'NOT_FOUND' }));
    if (
      proposal.status === 'APPROVED' ||
      proposal.status === 'REJECTED' ||
      proposal.status === 'CANCELLED'
    ) {
      return throwError(() => ({
        status: 409,
        error: 'INVALID_TRANSITION',
        message: 'Cannot add requested objects to a decided proposal',
      }));
    }
    const now = new Date().toISOString();
    const added: RequestedObject[] = request.objects.map((o) => ({
      id: `reqobj-${this.nextId++}`,
      objectReference: {
        inventoryNumber: o.inventoryNumber,
        displayTitle: o.displayTitle,
        objectName: o.objectName,
        briefDescriptionSnapshot: o.briefDescriptionSnapshot ?? null,
        collectionId: o.collectionId ?? null,
        collectionName: o.collectionName ?? null,
      },
      category: o.category ?? '',
      description: o.description ?? '',
      requestedAt: now,
    }));
    const updated: ProposalDetail = {
      ...proposal,
      requestedObjects: [...proposal.requestedObjects, ...added],
    };
    this.proposals.set(proposalId, updated);
    return of(updated);
  }

  removeRequestedObject(proposalId: string, requestedObjectId: string): Observable<void> {
    const proposal = this.proposals.get(proposalId);
    if (!proposal) return throwError(() => ({ status: 404, error: 'NOT_FOUND' }));
    if (
      proposal.status === 'APPROVED' ||
      proposal.status === 'REJECTED' ||
      proposal.status === 'CANCELLED'
    ) {
      return throwError(() => ({
        status: 409,
        error: 'INVALID_TRANSITION',
        message: 'Cannot remove requested objects from a decided proposal',
      }));
    }
    if (!proposal.requestedObjects.some((object) => object.id === requestedObjectId)) {
      return throwError(() => ({
        status: 404,
        error: 'NOT_FOUND',
        message: `Requested object ${requestedObjectId} not found on this proposal`,
      }));
    }
    this.proposals.set(proposalId, {
      ...proposal,
      requestedObjects: proposal.requestedObjects.filter(
        (object) => object.id !== requestedObjectId,
      ),
    });
    return of(undefined);
  }

  uploadDocument(proposalId: string, _file: File, documentType: string): Observable<Document> {
    const proposal = this.proposals.get(proposalId);
    if (!proposal) return throwError(() => ({ status: 404, error: 'NOT_FOUND' }));
    const now = new Date().toISOString();
    const doc: Document = {
      id: `doc-${this.nextId++}`,
      type: documentType,
      fileName: _file.name,
      fileReference: `mock-proposal-file-${this.nextId++}`,
      submittedAt: now,
      submittedBy: this.currentPrincipal(),
    };
    const updated: ProposalDetail = { ...proposal, documents: [...proposal.documents, doc] };
    this.proposals.set(proposalId, updated);
    this.pushEvent(proposalId, {
      occurredAt: now,
      type: 'DOCUMENTS_SUBMITTED',
      triggeredBy: this.currentPrincipal(),
      note: null,
    });
    return of(doc);
  }

  listDocuments(proposalId: string): Observable<ProposalDocumentsResponse> {
    const proposal = this.proposals.get(proposalId);
    if (!proposal) return throwError(() => ({ status: 404, error: 'NOT_FOUND' }));
    return of({ proposalId, documents: proposal.documents });
  }

  requestDocumentCorrections(
    proposalId: string,
    request: RequestDocumentCorrectionsRequest,
  ): Observable<ProposalCommandResult> {
    const proposal = this.proposals.get(proposalId);
    if (!proposal) return throwError(() => ({ status: 404, error: 'NOT_FOUND' }));
    const now = new Date().toISOString();
    const requestedBy = this.currentPrincipal();
    const newItems: DocumentCorrectionItem[] = request.items.map((item, index) => ({
      id: `corr-${this.nextId++}-${index}`,
      documentType: item.documentType,
      reason: item.reason,
      status: 'REQUESTED',
      requestedAt: now,
      requestedBy,
      documentId: item.documentId,
    }));
    const updated: ProposalDetail = {
      ...proposal,
      correctionItems: [...(proposal.correctionItems ?? []), ...newItems],
    };
    this.proposals.set(proposalId, updated);
    const evt: ProposalEvent = {
      occurredAt: now,
      type: 'DOCUMENT_CORRECTIONS_REQUESTED',
      triggeredBy: requestedBy,
      note: request.note || null,
    };
    this.pushEvent(proposalId, evt);
    return of({ id: proposalId, status: proposal.status, lastEvent: evt });
  }

  downloadDocument(proposalId: string, documentId: string): Observable<Blob> {
    const proposal = this.proposals.get(proposalId);
    if (!proposal) return throwError(() => ({ status: 404, error: 'NOT_FOUND' }));
    return of(new Blob([`mock document content for ${documentId}`], { type: 'text/plain' }));
  }

  listEvents(proposalId: string, query: PageQuery = {}): Observable<ProposalEventsPage> {
    const evts = [...(this.events.get(proposalId) ?? [])].sort(
      (left, right) => Date.parse(right.occurredAt) - Date.parse(left.occurredAt),
    );
    return of({ ...makePageFrom(evts, query), proposalId });
  }

  getConversation(proposalId: string, query: PageQuery = {}): Observable<Conversation> {
    const proposal = this.proposals.get(proposalId);
    if (!proposal) return throwError(() => ({ status: 404, error: 'NOT_FOUND' }));
    const msgs = this.messages.get(proposal.conversationId) ?? [];
    const page = makePageFrom(msgs, query);
    return of({
      conversationId: proposal.conversationId,
      proposalId,
      messages: page.content,
      page: page.page,
      size: page.size,
      totalElements: page.totalElements,
      totalPages: page.totalPages,
    });
  }

  sendMessage(proposalId: string, request: SendMessageRequest): Observable<Message> {
    const proposal = this.proposals.get(proposalId);
    if (!proposal) return throwError(() => ({ status: 404, error: 'NOT_FOUND' }));
    const attachments = this.resolveMessageAttachments(proposal, request.documentIds ?? []);
    const msg: Message = {
      id: `msg-${this.nextId++}`,
      sentAt: new Date().toISOString(),
      sender: this.currentPrincipal().user.email,
      recipient: request.recipient,
      subject: request.subject,
      body: request.body,
      attachments: attachments.length > 0 ? attachments : undefined,
    };
    const convMsgs = this.messages.get(proposal.conversationId) ?? [];
    convMsgs.push(msg);
    this.messages.set(proposal.conversationId, convMsgs);
    return of(msg);
  }

  private resolveMessageAttachments(
    proposal: ProposalDetail,
    documentIds: readonly string[],
  ): MessageAttachment[] {
    if (!documentIds.length) return [];

    const requested = new Set(documentIds);
    return proposal.documents
      .filter((document) => requested.has(document.id))
      .map((document) => ({
        documentId: document.id,
        fileName: document.fileName,
      }));
  }

  assignProposal(
    proposalId: string,
    request: AssignProposalRequest,
  ): Observable<ProposalAssignmentResult> {
    const proposal = this.proposals.get(proposalId);
    if (!proposal) return throwError(() => ({ status: 404, error: 'NOT_FOUND' }));
    const now = new Date().toISOString();
    const assignedTo = request.targetPermissionId
      ? (this.findPrincipalByPermissionId(request.targetPermissionId) ?? P['bob'])
      : this.currentPrincipal();
    const evt: ProposalEvent = {
      occurredAt: now,
      type: 'ASSIGNED',
      triggeredBy: this.currentPrincipal(),
      note: request.note || null,
    };
    this.proposals.set(proposalId, { ...proposal, status: 'PENDING', assignedTo });
    this.projectState.syncProposalStatus(
      proposalId,
      'PENDING',
      assignedTo,
      this.currentPrincipal(),
    );
    this.pushEvent(proposalId, evt);
    return of({ id: proposalId, status: 'PENDING', assignedTo, lastEvent: evt });
  }

  forwardProposal(
    proposalId: string,
    request: ForwardProposalRequest,
  ): Observable<ProposalAssignmentResult> {
    const proposal = this.proposals.get(proposalId);
    if (!proposal) return throwError(() => ({ status: 404, error: 'NOT_FOUND' }));
    const now = new Date().toISOString();
    const assignedTo = this.findPrincipalByPermissionId(request.targetPermissionId) ?? P['carol'];
    const evt: ProposalEvent = {
      occurredAt: now,
      type: 'FORWARDED',
      triggeredBy: this.currentPrincipal(),
      note: request.note || null,
    };
    this.proposals.set(proposalId, { ...proposal, assignedTo });
    this.projectState.syncProposalStatus(
      proposalId,
      proposal.status,
      assignedTo,
      this.currentPrincipal(),
    );
    this.pushEvent(proposalId, evt);
    return of({ id: proposalId, status: proposal.status, assignedTo, lastEvent: evt });
  }

  referProposalToDirection(
    proposalId: string,
    request: ReferProposalToDirectionRequest,
  ): Observable<ProposalAssignmentResult> {
    return this.directionTransfer(
      proposalId,
      request,
      'REFERRED_TO_DIRECTION',
      ['DIRECTION'],
      ['CURATORIAL', 'COLLECTIONS_MANAGEMENT'],
    );
  }

  returnProposalToStaff(
    proposalId: string,
    request: ReturnProposalToStaffRequest,
  ): Observable<ProposalAssignmentResult> {
    return this.directionTransfer(
      proposalId,
      request,
      'DIRECTION_CLARIFIED',
      ['CURATORIAL', 'COLLECTIONS_MANAGEMENT'],
      ['DIRECTION'],
    );
  }

  approveProposal(
    proposalId: string,
    request: ApproveProposalRequest,
  ): Observable<ProposalDecisionResult> {
    const proposal = this.proposals.get(proposalId);
    if (!proposal) return throwError(() => ({ status: 404, error: 'NOT_FOUND' }));
    const now = new Date().toISOString();
    const evt: ProposalEvent = {
      occurredAt: now,
      type: 'APPROVED',
      triggeredBy: this.currentPrincipal(),
      note: request.note || null,
    };
    const collectionUseProject = this.projectState.materializeProjectForProposal(
      proposal,
      request,
      now,
    );
    const updated = {
      ...proposal,
      status: 'APPROVED' as const,
      collectionUseProject,
    };
    this.proposals.set(proposalId, updated);
    this.pushEvent(proposalId, evt);
    return of({
      proposal: { id: proposalId, status: 'APPROVED', lastEvent: evt },
      collectionUseProject,
    });
  }

  rejectProposal(
    proposalId: string,
    request: ProposalReasonRequest,
  ): Observable<ProposalDecisionResult> {
    const proposal = this.proposals.get(proposalId);
    if (!proposal) return throwError(() => ({ status: 404, error: 'NOT_FOUND' }));
    const now = new Date().toISOString();
    const evt: ProposalEvent = {
      occurredAt: now,
      type: 'REJECTED',
      triggeredBy: this.currentPrincipal(),
      note: request.reason,
    };
    const collectionUseProject = proposal.collectionUseProject
      ? { ...proposal.collectionUseProject, status: 'CANCELLED' as const }
      : null;
    this.proposals.set(proposalId, {
      ...proposal,
      status: 'REJECTED',
      ...(collectionUseProject ? { collectionUseProject } : {}),
    });
    this.projectState.syncProposalStatus(
      proposalId,
      'REJECTED',
      proposal.assignedTo,
      this.currentPrincipal(),
    );
    this.pushEvent(proposalId, evt);
    return of({
      proposal: { id: proposalId, status: 'REJECTED', lastEvent: evt },
      collectionUseProject,
    });
  }

  cancelProposal(
    proposalId: string,
    request: ProposalReasonRequest,
  ): Observable<ProposalCancellationResult> {
    const proposal = this.proposals.get(proposalId);
    if (!proposal) return throwError(() => ({ status: 404, error: 'NOT_FOUND' }));
    if (proposal.status === 'REJECTED') {
      return throwError(() => ({
        status: 422,
        error: 'VALIDATION_ERROR',
        message: 'Cannot cancel a rejected proposal',
      }));
    }

    const now = new Date().toISOString();
    const evt: ProposalEvent = {
      occurredAt: now,
      type: 'CANCELLED',
      triggeredBy: this.currentPrincipal(),
      note: request.reason,
    };
    const hadProject =
      proposal.collectionUseProject?.status === 'IN_PROGRESS' ||
      proposal.collectionUseProject?.status === 'COMPLETED' ||
      proposal.status === 'APPROVED';
    const updated: ProposalDetail = {
      ...proposal,
      status: 'CANCELLED',
      collectionUseProject: proposal.collectionUseProject
        ? { ...proposal.collectionUseProject, status: 'CANCELLED' }
        : proposal.collectionUseProject,
    };
    this.proposals.set(proposalId, updated);
    this.projectState.syncProposalStatus(
      proposalId,
      'CANCELLED',
      proposal.assignedTo,
      this.currentPrincipal(),
    );
    this.pushEvent(proposalId, evt);

    return of({
      proposal: {
        id: proposalId,
        referenceNumber: proposal.referenceNumber,
        title: proposal.title,
        status: 'CANCELLED',
        beginDate: proposal.beginDate,
        endDate: proposal.endDate,
        assignedTo: proposal.assignedTo,
        lastEvent: evt,
      },
      collectionUseProject:
        hadProject && proposal.collectionUseProject
          ? { ...proposal.collectionUseProject, status: 'CANCELLED' }
          : null,
    });
  }

  private pushEvent(proposalId: string, evt: ProposalEvent): void {
    const evts = this.events.get(proposalId) ?? [];
    evts.push(evt);
    this.events.set(proposalId, evts);
  }

  private directionTransfer(
    proposalId: string,
    request: ReferProposalToDirectionRequest | ReturnProposalToStaffRequest,
    eventType: 'REFERRED_TO_DIRECTION' | 'DIRECTION_CLARIFIED',
    targetGroups: readonly PermissionPrincipal['group'][],
    callerGroups: readonly PermissionPrincipal['group'][],
  ): Observable<ProposalAssignmentResult> {
    const proposal = this.proposals.get(proposalId);
    const caller = this.currentPrincipal();
    const target = this.findPrincipalByPermissionId(request.targetPermissionId);
    if (!proposal) return throwError(() => ({ status: 404, error: 'NOT_FOUND' }));
    if (!callerGroups.includes(caller.group)) {
      return throwError(() => ({ status: 403, error: 'INSUFFICIENT_GROUP' }));
    }
    if (proposal.status !== 'PENDING' || proposal.assignedTo?.permissionId !== caller.permissionId) {
      return throwError(() => ({ status: 409, error: 'INVALID_TRANSITION' }));
    }
    if (!request.reason.trim()) {
      return throwError(() => ({ status: 422, error: 'VALIDATION_ERROR' }));
    }
    if (!target || !targetGroups.includes(target.group)) {
      return throwError(() => ({ status: 422, error: 'INVALID_PERMISSION_TARGET' }));
    }
    const evt: ProposalEvent = {
      occurredAt: new Date().toISOString(),
      type: eventType,
      triggeredBy: caller,
      targetPermission: target,
      note: request.reason.trim(),
    };
    this.proposals.set(proposalId, { ...proposal, assignedTo: target });
    this.pushEvent(proposalId, evt);
    return of({ id: proposalId, status: proposal.status, assignedTo: target, lastEvent: evt });
  }

  private currentPrincipal(): PermissionPrincipal {
    const session = this.identity.session();
    const permission = session
      ? MOCK_USERS.find(
          (u) => u.id === session.user.id || u.email === session.user.email,
        )?.permissions.find((p) => p.group.name === session.group)
      : null;

    if (!session || !permission) return P['bob'];

    return {
      permissionId: permission.permissionId,
      user: {
        id: session.user.id,
        name: session.user.displayName,
        email: session.user.email,
      },
      group: permission.group.name,
    };
  }

  private findPrincipalByPermissionId(permissionId: string): PermissionPrincipal | null {
    const user = MOCK_USERS.find((u) => u.permissions.some((p) => p.permissionId === permissionId));
    const permission = user?.permissions.find((p) => p.permissionId === permissionId);

    if (!user || !permission) return null;

    return {
      permissionId,
      user: { id: user.id, name: user.name, email: user.email },
      group: permission.group.name,
    };
  }
}
