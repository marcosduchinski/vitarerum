import { inject, Injectable } from '@angular/core';
import { GroupName } from '@core/auth/models/group-name.enum';
import { IDENTITY_SERVICE } from '@core/auth/identity.service';
import { Page } from '@shared/models/page.model';
import { Observable, of, throwError } from 'rxjs';

import { MediaType, UseResult, UseStatus } from '@shared/models/collection-use-status.model';
import {
  Attachment,
  CollectionUseProjectDetail,
  CollectionUseProjectSummary,
  CreateObjectLogEntryRequest,
  CreateObjectOccurrenceEntryRequest,
  NoteRequest,
  ObjectAccessLog,
  ObjectLogEntriesPage,
  ObjectLogEntriesQuery,
  ObjectLogEntry,
  ObjectOccurrenceEntriesPage,
  ObjectOccurrenceEntriesQuery,
  ObjectOccurrenceEntry,
  ObjectOccurrenceLog,
  ProjectActionPermissions,
  ProjectEventsPage,
  ProjectEventsQuery,
  ProjectListQuery,
  ProjectStaffContext,
  PublicationEntriesPage,
  PublicationEntriesQuery,
  PublicationLog,
  PublicationLogEntry,
  ReasonRequest,
  UpdateObjectLogEntryRequest,
  UpdateObjectOccurrenceEntryRequest,
  UseEvent,
} from '../models/project.model';
import { ProjectTransitionResult } from '../services/project-api.service';
import {
  makePageFrom,
  MockProjectState,
  MutableProjectState,
  P,
} from '@features/collections/proposals/mocks/mock-data';

@Injectable()
export class ProjectApiServiceMock {
  private readonly state = inject(MockProjectState);
  private readonly identity = inject(IDENTITY_SERVICE);

  listProjects(query: ProjectListQuery = {}): Observable<Page<CollectionUseProjectSummary>> {
    let items = [...this.state.projects.values()];

    if (query.status) items = items.filter((p) => p.status === query.status);
    if (query.type) items = items.filter((p) => p.type === query.type);
    // Mirror the backend scoping rule: staff may filter by any `requestedBy`,
    // while non-staff callers are always forced to their own permissionId
    // regardless of (or in the absence of) the query parameter.
    const requestedByScope = this.identity.isStaff()
      ? query.requestedBy
      : (this.identity.getPermissionId() ?? '\0');
    if (requestedByScope)
      items = items.filter((p) => p.requestedBy.permissionId === requestedByScope);
    if (query.assignedTo)
      items = items.filter((p) => p.proposalAssignedTo?.permissionId === query.assignedTo);
    if (query.search) {
      const q = query.search.toLowerCase();
      items = items.filter(
        (p) => p.title.toLowerCase().includes(q) || p.referenceNumber.toLowerCase().includes(q),
      );
    }

    const summaries: CollectionUseProjectSummary[] = items.map((p) => this.toSummary(p));
    return of(makePageFrom(summaries, query));
  }

  getProject(projectId: string): Observable<CollectionUseProjectDetail> {
    const p = this.state.projects.get(projectId);
    if (!p) return throwError(() => ({ status: 404, error: 'NOT_FOUND' }));
    return of(this.toDetail(p));
  }

  startProject(projectId: string, request: NoteRequest): Observable<ProjectTransitionResult> {
    return this.transition(projectId, ['CREATED'], 'IN_PROGRESS', 'STARTED', request.note);
  }

  completeProject(projectId: string, request: NoteRequest): Observable<ProjectTransitionResult> {
    return this.transition(projectId, ['IN_PROGRESS'], 'COMPLETED', 'COMPLETED', request.note);
  }

  cancelProject(projectId: string, request: ReasonRequest): Observable<ProjectTransitionResult> {
    return this.transition(
      projectId,
      ['CREATED', 'IN_PROGRESS'],
      'CANCELLED',
      'CANCELLED',
      request.reason,
    );
  }

  createObjectLogEntry(
    projectId: string,
    request: CreateObjectLogEntryRequest,
  ): Observable<ObjectLogEntry> {
    const p = this.state.projects.get(projectId);
    if (!p) return throwError(() => ({ status: 404, error: 'NOT_FOUND' }));
    const currentPrincipal = this.currentPrincipal();
    if (currentPrincipal.group === 'EXTERNAL' && p.status !== 'IN_PROGRESS') {
      return throwError(() => ({
        status: 409,
        error: 'INVALID_TRANSITION',
        message: 'Entries can only be added while the project is IN_PROGRESS',
      }));
    }
    this.ensureObjectAccessLog(projectId);
    const entry: ObjectLogEntry = {
      id: this.state.nextEntryId(),
      objectReference: {
        inventoryNumber: request.inventoryNumber,
        displayTitle: null,
        objectName: null,
        briefDescriptionSnapshot: null,
      },
      numberOfObjects: request.numberOfObjects,
      addedAt: new Date().toISOString(),
      addedBy: currentPrincipal,
      observations: request.observations ?? null,
      requestedObjectId: request.requestedObjectId ?? null,
      attachments: [],
    };
    const current = this.state.logEntries.get(projectId) ?? [];
    current.push(entry);
    this.state.logEntries.set(projectId, current);
    return of(entry);
  }

  updateObjectLogEntry(
    projectId: string,
    entryId: string,
    request: UpdateObjectLogEntryRequest,
  ): Observable<ObjectLogEntry> {
    const p = this.state.projects.get(projectId);
    if (!p) return throwError(() => ({ status: 404, error: 'NOT_FOUND' }));
    if (this.currentPrincipal().group === 'EXTERNAL' && p.status !== 'IN_PROGRESS') {
      return throwError(() => ({
        status: 409,
        error: 'INVALID_TRANSITION',
        message: 'Entries can only be edited while the project is IN_PROGRESS',
      }));
    }
    if (request.numberOfObjects !== undefined && request.numberOfObjects < 1) {
      return throwError(() => ({ status: 422, error: 'VALIDATION_ERROR' }));
    }

    const allEntries = this.state.logEntries.get(projectId) ?? [];
    const idx = allEntries.findIndex((e) => e.id === entryId);
    if (idx < 0) {
      return throwError(() => ({
        status: 404,
        error: 'ENTRY_NOT_FOUND',
        message: `No entry found with id ${entryId}`,
      }));
    }

    const current = allEntries[idx];
    const updated: ObjectLogEntry = {
      ...current,
      ...(request.addedAt !== undefined ? { addedAt: request.addedAt } : {}),
      ...(request.numberOfObjects !== undefined
        ? { numberOfObjects: request.numberOfObjects }
        : {}),
      ...(request.observations !== undefined ? { observations: request.observations } : {}),
    };
    allEntries[idx] = updated;
    this.state.logEntries.set(projectId, allEntries);
    return of(updated);
  }

  listObjectLogEntries(
    projectId: string,
    query: ObjectLogEntriesQuery = {},
  ): Observable<ObjectLogEntriesPage> {
    const p = this.state.projects.get(projectId);
    if (!p) return throwError(() => ({ status: 404, error: 'NOT_FOUND' }));
    let items = this.state.logEntries.get(projectId) ?? [];
    if (query.addedBy) items = items.filter((e) => e.addedBy.permissionId === query.addedBy);
    return of({
      ...makePageFrom(items, query),
      projectId,
      accessLog: this.state.objectAccessLogs.get(projectId) ?? null,
    });
  }

  getObjectAccessLog(projectId: string): Observable<ObjectAccessLog> {
    const p = this.state.projects.get(projectId);
    if (!p) return throwError(() => ({ status: 404, error: 'NOT_FOUND' }));
    const accessLog = this.state.objectAccessLogs.get(projectId);
    if (!accessLog) {
      return throwError(() => ({
        status: 404,
        error: 'OBJECT_ACCESS_LOG_NOT_FOUND',
        message: 'No object_access_log found with id uuid',
      }));
    }
    return of(accessLog);
  }

  uploadLogEntryAttachment(
    projectId: string,
    entryId: string,
    file: File,
    mediaType: MediaType,
  ): Observable<Attachment> {
    const p = this.state.projects.get(projectId);
    if (!p) return throwError(() => ({ status: 404, error: 'NOT_FOUND' }));
    if (this.currentPrincipal().group === 'EXTERNAL' && p.status !== 'IN_PROGRESS') {
      return throwError(() => ({
        status: 409,
        error: 'INVALID_TRANSITION',
        message: 'Entries can only be added while the project is IN_PROGRESS',
      }));
    }
    const allEntries = this.state.logEntries.get(projectId) ?? [];
    const entry = allEntries.find((e) => e.id === entryId);
    if (!entry) return throwError(() => ({ status: 404, error: 'NOT_FOUND' }));
    const attachment: Attachment = {
      fileReference: this.state.nextFileReference(),
      fileName: file.name,
      mediaType,
      uploadedAt: new Date().toISOString(),
    };
    const idx = allEntries.findIndex((e) => e.id === entryId);
    allEntries[idx] = { ...entry, attachments: [...entry.attachments, attachment] };
    this.state.logEntries.set(projectId, allEntries);
    return of(attachment);
  }

  // The mock holds no real bytes, so it streams a small synthetic file named
  // after the attachment — enough to exercise the download flow in mock mode.
  // Mirrors the backend 404s when the entry or fileReference is unknown.
  downloadLogEntryAttachment(
    projectId: string,
    entryId: string,
    fileReference: string,
  ): Observable<Blob> {
    const entry = (this.state.logEntries.get(projectId) ?? []).find((e) => e.id === entryId);
    if (!entry) return throwError(() => ({ status: 404, error: 'ENTRY_NOT_FOUND' }));
    const attachment = entry.attachments.find((a) => a.fileReference === fileReference);
    if (!attachment) return throwError(() => ({ status: 404, error: 'ATTACHMENT_NOT_FOUND' }));
    return of(this.mockAttachmentBlob(attachment.fileName));
  }

  createObjectOccurrenceEntry(
    projectId: string,
    request: CreateObjectOccurrenceEntryRequest,
  ): Observable<ObjectOccurrenceEntry> {
    const p = this.state.projects.get(projectId);
    if (!p) return throwError(() => ({ status: 404, error: 'NOT_FOUND' }));
    const currentPrincipal = this.currentPrincipal();
    if (currentPrincipal.group === 'EXTERNAL' && p.status !== 'IN_PROGRESS') {
      return throwError(() => ({
        status: 409,
        error: 'INVALID_TRANSITION',
        message: 'Entries can only be added while the project is IN_PROGRESS',
      }));
    }
    this.ensureObjectOccurrenceLog(projectId);
    const entry: ObjectOccurrenceEntry = {
      id: this.state.nextEntryId(),
      objectReference: {
        inventoryNumber: request.inventoryNumber,
        displayTitle: null,
        objectName: null,
        briefDescriptionSnapshot: null,
      },
      numberOfObjects: request.numberOfObjects,
      occurrenceDate: request.occurrenceDate,
      location: request.location,
      reportedBy: currentPrincipal,
      detailedDescription: request.detailedDescription,
      testimonial: request.testimonial ?? null,
      requestedObjectId: request.requestedObjectId ?? null,
      attachments: [],
    };
    const current = this.state.occurrenceEntries.get(projectId) ?? [];
    current.push(entry);
    this.state.occurrenceEntries.set(projectId, current);
    return of(entry);
  }

  listObjectOccurrenceEntries(
    projectId: string,
    query: ObjectOccurrenceEntriesQuery = {},
  ): Observable<ObjectOccurrenceEntriesPage> {
    const p = this.state.projects.get(projectId);
    if (!p) return throwError(() => ({ status: 404, error: 'NOT_FOUND' }));
    let items = this.state.occurrenceEntries.get(projectId) ?? [];
    if (query.reportedBy) {
      items = items.filter((e) => e.reportedBy.permissionId === query.reportedBy);
    }
    return of({
      ...makePageFrom(items, query),
      projectId,
      occurrenceLog: this.state.objectOccurrenceLogs.get(projectId) ?? null,
    });
  }

  updateObjectOccurrenceEntry(
    projectId: string,
    entryId: string,
    request: UpdateObjectOccurrenceEntryRequest,
  ): Observable<ObjectOccurrenceEntry> {
    const p = this.state.projects.get(projectId);
    if (!p) return throwError(() => ({ status: 404, error: 'NOT_FOUND' }));
    if (this.currentPrincipal().group === 'EXTERNAL' && p.status !== 'IN_PROGRESS') {
      return throwError(() => ({
        status: 409,
        error: 'INVALID_TRANSITION',
        message: 'Entries can only be edited while the project is IN_PROGRESS',
      }));
    }
    if (request.numberOfObjects !== undefined && request.numberOfObjects < 1) {
      return throwError(() => ({ status: 422, error: 'VALIDATION_ERROR' }));
    }
    if (request.location !== undefined && !request.location.trim()) {
      return throwError(() => ({ status: 422, error: 'VALIDATION_ERROR' }));
    }
    if (request.detailedDescription !== undefined && !request.detailedDescription.trim()) {
      return throwError(() => ({ status: 422, error: 'VALIDATION_ERROR' }));
    }

    const allEntries = this.state.occurrenceEntries.get(projectId) ?? [];
    const idx = allEntries.findIndex((e) => e.id === entryId);
    if (idx < 0) {
      return throwError(() => ({
        status: 404,
        error: 'ENTRY_NOT_FOUND',
        message: `No entry found with id ${entryId}`,
      }));
    }

    const current = allEntries[idx];
    const updated: ObjectOccurrenceEntry = {
      ...current,
      ...(request.numberOfObjects !== undefined
        ? { numberOfObjects: request.numberOfObjects }
        : {}),
      ...(request.occurrenceDate !== undefined ? { occurrenceDate: request.occurrenceDate } : {}),
      ...(request.location !== undefined ? { location: request.location } : {}),
      ...(request.detailedDescription !== undefined
        ? { detailedDescription: request.detailedDescription }
        : {}),
      ...(request.testimonial !== undefined ? { testimonial: request.testimonial } : {}),
    };
    allEntries[idx] = updated;
    this.state.occurrenceEntries.set(projectId, allEntries);
    return of(updated);
  }

  getObjectOccurrenceLog(projectId: string): Observable<ObjectOccurrenceLog> {
    const p = this.state.projects.get(projectId);
    if (!p) return throwError(() => ({ status: 404, error: 'NOT_FOUND' }));
    const occurrenceLog = this.state.objectOccurrenceLogs.get(projectId);
    if (!occurrenceLog) {
      return throwError(() => ({
        status: 404,
        error: 'OBJECT_OCCURRENCE_LOG_NOT_FOUND',
        message: 'No object_occurrence_log found with id uuid',
      }));
    }
    return of(occurrenceLog);
  }

  uploadOccurrenceEntryAttachment(
    projectId: string,
    entryId: string,
    file: File,
    mediaType: MediaType,
  ): Observable<Attachment> {
    const p = this.state.projects.get(projectId);
    if (!p) return throwError(() => ({ status: 404, error: 'NOT_FOUND' }));
    if (this.currentPrincipal().group === 'EXTERNAL' && p.status !== 'IN_PROGRESS') {
      return throwError(() => ({
        status: 409,
        error: 'INVALID_TRANSITION',
        message: 'Entries can only be added while the project is IN_PROGRESS',
      }));
    }
    const allEntries = this.state.occurrenceEntries.get(projectId) ?? [];
    const entry = allEntries.find((e) => e.id === entryId);
    if (!entry) return throwError(() => ({ status: 404, error: 'NOT_FOUND' }));
    const attachment: Attachment = {
      fileReference: this.state.nextFileReference(),
      fileName: file.name,
      mediaType,
      uploadedAt: new Date().toISOString(),
    };
    const idx = allEntries.findIndex((e) => e.id === entryId);
    allEntries[idx] = { ...entry, attachments: [...entry.attachments, attachment] };
    this.state.occurrenceEntries.set(projectId, allEntries);
    return of(attachment);
  }

  // See downloadLogEntryAttachment — streams a synthetic file in mock mode.
  downloadOccurrenceEntryAttachment(
    projectId: string,
    entryId: string,
    fileReference: string,
  ): Observable<Blob> {
    const entry = (this.state.occurrenceEntries.get(projectId) ?? []).find((e) => e.id === entryId);
    if (!entry) return throwError(() => ({ status: 404, error: 'ENTRY_NOT_FOUND' }));
    const attachment = entry.attachments.find((a) => a.fileReference === fileReference);
    if (!attachment) return throwError(() => ({ status: 404, error: 'ATTACHMENT_NOT_FOUND' }));
    return of(this.mockAttachmentBlob(attachment.fileName));
  }

  private mockAttachmentBlob(fileName: string): Blob {
    return new Blob([`Mock attachment content for ${fileName}\n`], { type: 'text/plain' });
  }

  createPublicationEntry(projectId: string, request: NoteRequest): Observable<PublicationLogEntry> {
    const p = this.state.projects.get(projectId);
    if (!p) return throwError(() => ({ status: 404, error: 'NOT_FOUND' }));
    const gate = this.publicationWriteError(p.status);
    if (gate) return throwError(() => gate);
    if (!request.note?.trim()) {
      return throwError(() => ({ status: 422, error: 'VALIDATION_ERROR' }));
    }
    this.ensurePublicationLog(projectId);
    const entry: PublicationLogEntry = {
      id: this.state.nextEntryId(),
      addedAt: new Date().toISOString(),
      addedBy: this.currentPrincipal(),
      note: request.note,
      attachments: [],
    };
    const current = this.state.publicationEntries.get(projectId) ?? [];
    current.push(entry);
    this.state.publicationEntries.set(projectId, current);
    return of(entry);
  }

  updatePublicationEntry(
    projectId: string,
    entryId: string,
    request: NoteRequest,
  ): Observable<PublicationLogEntry> {
    const p = this.state.projects.get(projectId);
    if (!p) return throwError(() => ({ status: 404, error: 'NOT_FOUND' }));
    const gate = this.publicationWriteError(p.status);
    if (gate) return throwError(() => gate);
    if (!request.note?.trim()) {
      return throwError(() => ({ status: 422, error: 'VALIDATION_ERROR' }));
    }
    const allEntries = this.state.publicationEntries.get(projectId) ?? [];
    const idx = allEntries.findIndex((e) => e.id === entryId);
    if (idx < 0) {
      return throwError(() => ({
        status: 404,
        error: 'ENTRY_NOT_FOUND',
        message: `No entry found with id ${entryId}`,
      }));
    }
    const updated: PublicationLogEntry = { ...allEntries[idx], note: request.note };
    allEntries[idx] = updated;
    this.state.publicationEntries.set(projectId, allEntries);
    return of(updated);
  }

  listPublicationEntries(
    projectId: string,
    query: PublicationEntriesQuery = {},
  ): Observable<PublicationEntriesPage> {
    const p = this.state.projects.get(projectId);
    if (!p) return throwError(() => ({ status: 404, error: 'NOT_FOUND' }));
    let items = this.state.publicationEntries.get(projectId) ?? [];
    if (query.addedBy) items = items.filter((e) => e.addedBy.permissionId === query.addedBy);
    return of({
      ...makePageFrom(items, query),
      projectId,
      publicationLog: this.state.publicationLogs.get(projectId) ?? null,
    });
  }

  getPublicationLog(projectId: string): Observable<PublicationLog> {
    const p = this.state.projects.get(projectId);
    if (!p) return throwError(() => ({ status: 404, error: 'NOT_FOUND' }));
    const publicationLog = this.state.publicationLogs.get(projectId);
    if (!publicationLog) {
      return throwError(() => ({
        status: 404,
        error: 'PUBLICATION_LOG_NOT_FOUND',
        message: 'No publication_log found with id uuid',
      }));
    }
    return of(publicationLog);
  }

  uploadPublicationEntryAttachment(
    projectId: string,
    entryId: string,
    file: File,
    mediaType: MediaType,
    note?: string,
  ): Observable<Attachment> {
    const p = this.state.projects.get(projectId);
    if (!p) return throwError(() => ({ status: 404, error: 'NOT_FOUND' }));
    const gate = this.publicationWriteError(p.status);
    if (gate) return throwError(() => gate);
    const allEntries = this.state.publicationEntries.get(projectId) ?? [];
    const entry = allEntries.find((e) => e.id === entryId);
    if (!entry) return throwError(() => ({ status: 404, error: 'ENTRY_NOT_FOUND' }));
    const attachment: Attachment = {
      fileReference: this.state.nextFileReference(),
      fileName: file.name,
      mediaType,
      uploadedAt: new Date().toISOString(),
      note: note ?? null,
    };
    const idx = allEntries.findIndex((e) => e.id === entryId);
    allEntries[idx] = { ...entry, attachments: [...entry.attachments, attachment] };
    this.state.publicationEntries.set(projectId, allEntries);
    return of(attachment);
  }

  // See downloadLogEntryAttachment — streams a synthetic file in mock mode.
  downloadPublicationEntryAttachment(
    projectId: string,
    entryId: string,
    fileReference: string,
  ): Observable<Blob> {
    const entry = (this.state.publicationEntries.get(projectId) ?? []).find(
      (e) => e.id === entryId,
    );
    if (!entry) return throwError(() => ({ status: 404, error: 'ENTRY_NOT_FOUND' }));
    const attachment = entry.attachments.find((a) => a.fileReference === fileReference);
    if (!attachment) return throwError(() => ({ status: 404, error: 'ATTACHMENT_NOT_FOUND' }));
    return of(this.mockAttachmentBlob(attachment.fileName));
  }

  // Publication entries flip the usual log gate: the external requester writes
  // while IN_PROGRESS; curatorial/collections/direction staff write once
  // COMPLETED. Any other status rejects everyone with 409. Returns the error to
  // throw, or null when the current caller may write.
  private publicationWriteError(
    status: UseStatus,
  ): { status: number; error: string; message: string } | null {
    const group = this.currentPrincipal().group;
    if (status === 'IN_PROGRESS') {
      return group === 'EXTERNAL'
        ? null
        : {
            status: 403,
            error: 'ACCESS_DENIED',
            message:
              'While the project is IN_PROGRESS only the external requester can add publication entries',
          };
    }
    if (status === 'COMPLETED') {
      return group === 'CURATORIAL' || group === 'COLLECTIONS_MANAGEMENT' || group === 'DIRECTION'
        ? null
        : {
            status: 403,
            error: 'ACCESS_DENIED',
            message:
              'Once the project is COMPLETED only curatorial, collections-management or direction staff can add publication entries',
          };
    }
    return {
      status: 409,
      error: 'INVALID_TRANSITION',
      message:
        'Publication entries can only be added while the project is IN_PROGRESS or COMPLETED',
    };
  }

  private ensurePublicationLog(projectId: string): PublicationLog {
    const current = this.state.publicationLogs.get(projectId);
    if (current) return current;
    const project = this.state.projects.get(projectId);
    const publicationLog: PublicationLog = {
      id: this.state.nextPublicationLogId(),
      referenceNumber: this.state.nextPublicationLogReference(),
      projectId,
      // Informational only — snapshot the proposal's assignee when known.
      curator: project?.proposalAssignedTo ?? null,
    };
    this.state.publicationLogs.set(projectId, publicationLog);
    return publicationLog;
  }

  listEvents(projectId: string, query: ProjectEventsQuery = {}): Observable<ProjectEventsPage> {
    let evts = this.state.events.get(projectId) ?? [];
    if (query.type) evts = evts.filter((e) => e.type === query.type);
    return of({ ...makePageFrom(evts, query), projectId });
  }

  private toSummary(p: MutableProjectState): CollectionUseProjectSummary {
    return {
      id: p.id,
      referenceNumber: p.referenceNumber,
      title: p.title,
      purpose: p.purpose,
      note: p.note ?? null,
      type: p.type,
      status: p.status,
      result: p.result ?? null,
      beginDate: p.beginDate,
      endDate: p.endDate,
      requestedBy: p.requestedBy,
      proposal: {
        id: p.proposalId,
        status: p.proposalStatus,
        assignedTo: p.proposalAssignedTo,
      },
    };
  }

  private toDetail(p: MutableProjectState): CollectionUseProjectDetail {
    const group = this.identity.session()?.group ?? null;
    const isStaffGroup = group !== null && group !== 'EXTERNAL';

    return {
      ...this.toSummary(p),
      actions: this.projectActions(p, group),
      staffContext: isStaffGroup
        ? this.staffContext(p, group as Exclude<GroupName, 'EXTERNAL'>)
        : null,
    };
  }

  private projectActions(
    p: MutableProjectState,
    group: GroupName | null,
  ): ProjectActionPermissions {
    const isExternal = group === 'EXTERNAL' || group === null;

    return {
      canStart: isExternal && p.status === 'CREATED',
      canComplete: isExternal && p.status === 'IN_PROGRESS',
      canCancel: p.status === 'CREATED' || p.status === 'IN_PROGRESS',
      canOpenLog: !isExternal || p.status === 'IN_PROGRESS',
      canCreateObjectLogEntry: isExternal ? p.status === 'IN_PROGRESS' : true,
      canCreateOccurrenceEntry: isExternal ? p.status === 'IN_PROGRESS' : true,
    };
  }

  private staffContext(p: MutableProjectState, viewerGroup: Exclude<GroupName, 'EXTERNAL'>) {
    const proposal = this.state.proposals.get(p.proposalId);
    const messages = proposal ? (this.state.messages.get(proposal.conversationId) ?? []) : [];
    const lastMessage = messages.at(-1);
    const proposalEvents = proposal ? (this.state.proposalEvents.get(proposal.id) ?? []) : [];
    const forwarded = proposalEvents.filter((event) => event.type === 'FORWARDED').at(-1);
    const clarified = proposalEvents
      .filter((event) => event.type === 'APPROVED' || event.type === 'REJECTED')
      .at(-1);
    const logEntries = this.state.logEntries.get(p.id) ?? [];
    const occurrenceEntries = this.state.occurrenceEntries.get(p.id) ?? [];
    const attachmentCount =
      logEntries.reduce((total, entry) => total + entry.attachments.length, 0) +
      occurrenceEntries.reduce((total, entry) => total + entry.attachments.length, 0);

    return {
      viewerGroup,
      proposal: {
        id: proposal?.id ?? p.proposalId,
        referenceNumber: proposal?.referenceNumber ?? p.referenceNumber,
        title: proposal?.title ?? p.title,
        status: proposal?.status ?? p.proposalStatus,
        submittedAt: proposal?.submittedAt ?? p.beginDate,
        submittedBy: proposal?.requestedBy ?? p.requestedBy,
        assignedTo: proposal?.assignedTo ?? p.proposalAssignedTo ?? null,
      },
      requestedObjects:
        proposal?.requestedObjects.map((item) => ({
          id: item.id,
          objectReference: item.objectReference,
          category: item.category,
          description: item.description,
          requestedAt: item.requestedAt,
          requestedBy: item.requestedBy,
        })) ?? [],
      requestedDocuments:
        proposal?.requestedDocuments?.map((item) => ({
          id: item.id,
          type: item.type,
          description: item.description,
          requestedAt: item.requestedAt,
          requestedBy: item.requestedBy,
        })) ?? [],
      documents:
        proposal?.documents.map((item) => ({
          id: item.id,
          type: item.type,
          fileName: item.fileName,
          fileReference: item.fileReference,
          submittedAt: item.submittedAt,
          submittedBy: item.submittedBy,
        })) ?? [],
      conversationSummary: proposal
        ? {
            conversationId: proposal.conversationId,
            totalMessages: messages.length,
            lastMessageAt: lastMessage?.sentAt ?? null,
            lastMessageBy: lastMessage ? this.principalByEmail(lastMessage.sender) : null,
          }
        : null,
      logSummary: {
        accessLog: this.state.objectAccessLogs.get(p.id) ?? null,
        occurrenceLog: this.state.objectOccurrenceLogs.get(p.id) ?? null,
        objectLogEntryCount: logEntries.length,
        occurrenceEntryCount: occurrenceEntries.length,
        attachmentCount,
      },
      directionContext:
        forwarded || clarified
          ? {
              latestQuestion: forwarded?.note ?? null,
              latestClarification: clarified?.note ?? null,
              referredAt: forwarded?.occurredAt ?? null,
              clarifiedAt: clarified?.occurredAt ?? null,
            }
          : null,
    } satisfies ProjectStaffContext;
  }

  private transition(
    projectId: string,
    allowedStatuses: readonly UseStatus[],
    newStatus: UseStatus,
    eventType: UseEvent['type'],
    note: string,
  ): Observable<ProjectTransitionResult> {
    const p = this.state.projects.get(projectId);
    if (!p) return throwError(() => ({ status: 404, error: 'NOT_FOUND' }));
    if (!allowedStatuses.includes(p.status)) {
      return throwError(() => ({
        status: 409,
        error: 'INVALID_TRANSITION',
        message: `Project must be ${allowedStatuses.join(' or ')} to transition to ${newStatus}`,
      }));
    }
    const now = new Date().toISOString();
    p.status = newStatus;
    const result: UseResult | null =
      newStatus === 'COMPLETED' ? 'COMPLETED' : newStatus === 'CANCELLED' ? 'CANCELLED' : null;
    p.result = result;
    const evt: UseEvent = {
      occurredAt: now,
      type: eventType,
      triggeredBy: this.currentPrincipal(),
      note: note || null,
    };
    const events = this.state.events.get(projectId) ?? [];
    events.push(evt);
    this.state.events.set(projectId, events);
    return of({
      id: projectId,
      referenceNumber: p.referenceNumber,
      status: newStatus,
      result,
      lastEvent: evt,
    });
  }

  private currentPrincipal() {
    const session = this.identity.session();
    return session
      ? (Object.values(P).find(
          (p) => p.user.id === session.user.id || p.user.email === session.user.email,
        ) ?? P['alice'])
      : P['alice'];
  }

  private principalByEmail(email: string) {
    return Object.values(P).find((p) => p.user.email === email) ?? null;
  }

  private ensureObjectAccessLog(projectId: string): ObjectAccessLog {
    const current = this.state.objectAccessLogs.get(projectId);
    if (current) return current;
    const accessLog: ObjectAccessLog = {
      id: this.state.nextObjectAccessLogId(),
      referenceNumber: this.state.nextObjectAccessLogReference(),
      projectId,
      curator: null,
    };
    this.state.objectAccessLogs.set(projectId, accessLog);
    return accessLog;
  }

  private ensureObjectOccurrenceLog(projectId: string): ObjectOccurrenceLog {
    const current = this.state.objectOccurrenceLogs.get(projectId);
    if (current) return current;
    const occurrenceLog: ObjectOccurrenceLog = {
      id: this.state.nextObjectOccurrenceLogId(),
      referenceNumber: this.state.nextObjectOccurrenceLogReference(),
      projectId,
      curator: null,
    };
    this.state.objectOccurrenceLogs.set(projectId, occurrenceLog);
    return occurrenceLog;
  }
}
