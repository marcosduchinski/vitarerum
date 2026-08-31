import { HttpClient } from '@angular/common/http';
import { inject, Injectable, InjectionToken } from '@angular/core';
import { PermissionPrincipal } from '@core/auth/models/permission.model';
import { API_BASE_URL } from '@core/config/app-config.model';
import { buildApiUrl } from '@core/http/api-url.util';
import { buildHttpParams } from '@core/http/http-params.util';
import { Page, PageQuery } from '@shared/models/page.model';
import { map, Observable } from 'rxjs';

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
  Message,
  ProposalDetail,
  ProposalDocumentsResponse,
  ProposalEventsPage,
  ProposalListQuery,
  ProposalSummary,
  RequestedObject,
  RequesterContact,
  SendMessageRequest,
  UpdateProposalResult,
} from '../models/proposal.model';

type WireRequestedObject = RequestedObject & {
  readonly inventoryNumber?: string;
  readonly displayTitle?: string | null;
  readonly objectName?: string | null;
  readonly briefDescriptionSnapshot?: string | null;
  readonly collectionId?: string | null;
  readonly collectionName?: string | null;
};

// Public proposals awaiting approval have no system user/permission yet: the
// backend sends `requestedBy`/`submittedBy`/`triggeredBy` as null. Synthesize a
// display-only EXTERNAL principal so templates keep rendering the requester.
function externalPrincipal(name: string, email: string): PermissionPrincipal {
  return { permissionId: '', user: { id: '', name, email }, group: 'EXTERNAL' };
}

const GENERIC_EXTERNAL = externalPrincipal('External requester', '');

function principalFromContact(contact?: RequesterContact | null): PermissionPrincipal {
  return contact ? externalPrincipal(contact.name, contact.email) : GENERIC_EXTERNAL;
}

// Normalizes a proposal summary into the shape the app reads:
//  - the bare `intendedUse` use type becomes flat `type`;
//  - null `requestedBy` (public, pre-approval) becomes principal from `requesterContact`.
function normalizeProposal<T extends ProposalSummary>(p: T): T {
  const type = p.type ?? p.intendedUse ?? 'OTHER';
  const requestedBy = p.requestedBy ?? principalFromContact(p.requesterContact);
  return { ...p, type, requestedBy };
}

function normalizeRequestedObject(object: WireRequestedObject): RequestedObject {
  if (object.objectReference) {
    return {
      ...object,
      objectReference: {
        ...object.objectReference,
        collectionId: object.objectReference.collectionId ?? object.collectionId ?? null,
        collectionName: object.objectReference.collectionName ?? object.collectionName ?? null,
      },
    };
  }
  return {
    id: object.id,
    objectReference: {
      inventoryNumber: object.inventoryNumber ?? '',
      displayTitle: object.displayTitle ?? null,
      objectName: object.objectName ?? null,
      briefDescriptionSnapshot: object.briefDescriptionSnapshot ?? null,
      collectionId: object.collectionId ?? null,
      collectionName: object.collectionName ?? null,
    },
    category: object.category,
    description: object.description,
    requestedAt: object.requestedAt,
    requestedBy: object.requestedBy,
  };
}

// Detail additionally backfills document uploaders: public submissions arrive
// with `submittedBy: null` until Identity provisions a requester at approval.
function normalizeProposalDetail(p: ProposalDetail): ProposalDetail {
  const fallback = principalFromContact(p.requesterContact);
  return {
    ...normalizeProposal(p),
    documents: (p.documents ?? []).map((d) =>
      d.submittedBy ? d : { ...d, submittedBy: fallback },
    ),
    requestedObjects: ((p.requestedObjects ?? []) as readonly WireRequestedObject[]).map((object) =>
      normalizeRequestedObject(object),
    ),
    correctionItems: p.correctionItems ?? [],
  };
}

export const PROPOSAL_API_SERVICE = new InjectionToken<ProposalApiService>('PROPOSAL_API_SERVICE');

@Injectable()
export class ProposalApiService {
  private readonly http = inject(HttpClient);
  private readonly apiBaseUrl = inject(API_BASE_URL);

  createProposal(request: CreateProposalRequest): Observable<CreateProposalResponse> {
    const form = new FormData();
    this.appendOptional(form, 'title', request.title);
    this.appendOptional(form, 'intendedUse', request.intendedUse);
    this.appendOptional(form, 'purpose', request.purpose);
    this.appendOptional(form, 'beginDate', request.beginDate);
    this.appendOptional(form, 'endDate', request.endDate);
    this.appendOptional(form, 'initialMessageRecipient', request.initialMessageRecipient);
    this.appendOptional(form, 'initialMessageSubject', request.initialMessageSubject);
    this.appendOptional(form, 'initialMessageBody', request.initialMessageBody);
    for (const document of request.documents ?? []) {
      form.append('documents', document, document.name);
    }
    return this.http.post<CreateProposalResponse>(this.url('/proposals'), form);
  }

  listProposals(query: ProposalListQuery = {}): Observable<Page<ProposalSummary>> {
    // The contract uses snake_case filter names; the TS query stays camelCase.
    const statuses = typeof query.status === 'string' ? [query.status] : (query.status ?? []);
    let params = statuses.reduce(
      (httpParams, status) => httpParams.append('status', status),
      buildHttpParams({}),
    );
    const remainingParams = buildHttpParams({
      type: query.type,
      requested_by: query.requestedBy,
      assigned_to: query.assignedTo,
      date_from: query.dateFrom,
      date_to: query.dateTo,
      search: query.search,
      page: query.page,
      size: query.size,
    });
    for (const key of remainingParams.keys()) {
      for (const value of remainingParams.getAll(key) ?? []) {
        params = params.append(key, value);
      }
    }

    return this.http
      .get<Page<ProposalSummary>>(this.url('/proposals'), {
        params,
      })
      .pipe(map((page) => ({ ...page, content: page.content.map((p) => normalizeProposal(p)) })));
  }

  getProposal(proposalId: string): Observable<ProposalDetail> {
    return this.http
      .get<ProposalDetail>(this.url(`/proposals/${proposalId}`))
      .pipe(map((p) => normalizeProposalDetail(p)));
  }

  updateProposal(
    proposalId: string,
    request: UpdateProposalRequest,
  ): Observable<UpdateProposalResult> {
    return this.http.patch<UpdateProposalResult>(this.url(`/proposals/${proposalId}`), request);
  }

  addRequestedObjects(
    proposalId: string,
    request: AddRequestedObjectsRequest,
  ): Observable<ProposalDetail> {
    return this.http
      .post<ProposalDetail>(this.url(`/proposals/${proposalId}/requested-objects`), request)
      .pipe(map((p) => normalizeProposalDetail(p)));
  }

  removeRequestedObject(proposalId: string, requestedObjectId: string): Observable<void> {
    return this.http.delete<void>(
      this.url(`/proposals/${proposalId}/requested-objects/${requestedObjectId}`),
    );
  }

  uploadDocument(proposalId: string, file: File, documentType: string): Observable<Document> {
    const body = new FormData();
    body.append('file', file);
    body.append('documentType', documentType);

    return this.http.post<Document>(this.url(`/proposals/${proposalId}/documents`), body);
  }

  listDocuments(proposalId: string): Observable<ProposalDocumentsResponse> {
    return this.http.get<ProposalDocumentsResponse>(this.url(`/proposals/${proposalId}/documents`));
  }

  // Staff asks the requester to correct/replace documents or supply missing ones.
  // Instructory: keeps the proposal PENDING (unlike reject) and e-mails the
  // requester a scoped amendment link. One call carries every staged item.
  requestDocumentCorrections(
    proposalId: string,
    request: RequestDocumentCorrectionsRequest,
  ): Observable<ProposalCommandResult> {
    return this.http.post<ProposalCommandResult>(
      this.url(`/proposals/${proposalId}/request-document-corrections`),
      request,
    );
  }

  // Downloads a single document's binary content. The endpoint streams the file
  // (Content-Disposition: attachment); the Bearer token is added by the auth
  // interceptor, so it must be fetched here rather than linked directly.
  downloadDocument(proposalId: string, documentId: string): Observable<Blob> {
    return this.http.get(this.url(`/proposals/${proposalId}/documents/${documentId}`), {
      responseType: 'blob',
    });
  }

  listEvents(proposalId: string, query: PageQuery = {}): Observable<ProposalEventsPage> {
    return this.http
      .get<ProposalEventsPage>(this.url(`/proposals/${proposalId}/events`), {
        params: buildHttpParams(query),
      })
      .pipe(
        // Public-submission events (e.g. SUBMITTED) come with a null actor until
        // Identity provisions one at approval; render a generic external actor.
        map((page) => ({
          ...page,
          content: page.content.map((event) =>
            event.triggeredBy ? event : { ...event, triggeredBy: GENERIC_EXTERNAL },
          ),
        })),
      );
  }

  getConversation(proposalId: string, query: PageQuery = {}): Observable<Conversation> {
    return this.http.get<Conversation>(this.url(`/proposals/${proposalId}/conversation`), {
      params: buildHttpParams(query),
    });
  }

  sendMessage(proposalId: string, request: SendMessageRequest): Observable<Message> {
    return this.http.post<Message>(
      this.url(`/proposals/${proposalId}/conversation/messages`),
      request,
    );
  }

  assignProposal(
    proposalId: string,
    request: AssignProposalRequest,
  ): Observable<ProposalAssignmentResult> {
    return this.http.post<ProposalAssignmentResult>(
      this.url(`/proposals/${proposalId}/assign`),
      request,
    );
  }

  forwardProposal(
    proposalId: string,
    request: ForwardProposalRequest,
  ): Observable<ProposalAssignmentResult> {
    return this.http.post<ProposalAssignmentResult>(
      this.url(`/proposals/${proposalId}/forward`),
      request,
    );
  }

  referProposalToDirection(
    proposalId: string,
    request: ReferProposalToDirectionRequest,
  ): Observable<ProposalAssignmentResult> {
    return this.http.post<ProposalAssignmentResult>(
      this.url(`/proposals/${proposalId}/refer-to-direction`),
      request,
    );
  }

  returnProposalToStaff(
    proposalId: string,
    request: ReturnProposalToStaffRequest,
  ): Observable<ProposalAssignmentResult> {
    return this.http.post<ProposalAssignmentResult>(
      this.url(`/proposals/${proposalId}/return-to-staff`),
      request,
    );
  }

  approveProposal(
    proposalId: string,
    request: ApproveProposalRequest,
  ): Observable<ProposalDecisionResult> {
    return this.http.post<ProposalDecisionResult>(
      this.url(`/proposals/${proposalId}/approve`),
      request,
    );
  }

  rejectProposal(
    proposalId: string,
    request: ProposalReasonRequest,
  ): Observable<ProposalDecisionResult> {
    return this.http.post<ProposalDecisionResult>(
      this.url(`/proposals/${proposalId}/reject`),
      request,
    );
  }

  // Researcher cancels their own proposal. Allowed from SUBMITTED/PENDING/APPROVED;
  // a linked project (if any) is cascaded to CANCELLED by the backend.
  cancelProposal(
    proposalId: string,
    request: ProposalReasonRequest,
  ): Observable<ProposalCancellationResult> {
    return this.http.post<ProposalCancellationResult>(
      this.url(`/proposals/${proposalId}/cancel`),
      request,
    );
  }

  private url(path: string): string {
    return buildApiUrl(this.apiBaseUrl, path);
  }

  private appendOptional(form: FormData, key: string, value: string | null | undefined): void {
    if (value !== null && value !== undefined) {
      form.append(key, value);
    }
  }
}
