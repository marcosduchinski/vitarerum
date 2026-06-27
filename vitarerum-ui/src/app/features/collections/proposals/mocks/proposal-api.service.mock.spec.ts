import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { firstValueFrom } from 'rxjs';

import { IDENTITY_SERVICE, IdentityService } from '@core/auth/identity.service';
import { GroupName } from '@core/auth/models/group-name.enum';
import { IdentitySession } from '@core/auth/models/identity-session.model';
import { LoginRequest } from '@core/auth/models/login.model';

import { ProjectApiServiceMock } from '../../projects/mocks/project-api.service.mock';
import { MOCK_SEED, MockProjectState, TEST_SEED } from './mock-data';
import { ProposalApiServiceMock } from './proposal-api.service.mock';

const sessionState = signal<IdentitySession | null>({
  accessToken: 'mock-token',
  user: {
    id: 'u-bob',
    email: 'bob@collections.example.com',
    displayName: 'Bob Santos',
  },
  group: 'COLLECTIONS_MANAGEMENT',
  availableGroups: ['COLLECTIONS_MANAGEMENT'],
});
const isStaffState = signal(true);

const identityStub: IdentityService = {
  session: sessionState.asReadonly(),
  isAuthenticated: signal(true).asReadonly(),
  isStaff: isStaffState.asReadonly(),
  signIn: async (credentials: LoginRequest) => {
    const session = sessionState();
    if (session) {
      sessionState.set({ ...session, user: { ...session.user, email: credentials.email } });
    }
  },
  signOut: () => sessionState.set(null),
  getAccessToken: () => sessionState()?.accessToken ?? null,
  getPermissionId: () => null,
  setGroup: (group: GroupName) => {
    const session = sessionState();
    if (session) sessionState.set({ ...session, group });
  },
  updateAvailableGroups: (groups: readonly GroupName[]) => {
    const session = sessionState();
    if (session) sessionState.set({ ...session, availableGroups: [...groups] });
  },
};

describe('ProposalApiServiceMock', () => {
  let service: ProposalApiServiceMock;

  beforeEach(() => {
    isStaffState.set(true);
    sessionState.set({
      accessToken: 'mock-token',
      user: {
        id: 'u-bob',
        email: 'bob@collections.example.com',
        displayName: 'Bob Santos',
      },
      group: 'COLLECTIONS_MANAGEMENT',
      availableGroups: ['COLLECTIONS_MANAGEMENT'],
    });

    TestBed.configureTestingModule({
      providers: [
        ProposalApiServiceMock,
        ProjectApiServiceMock,
        MockProjectState,
        { provide: MOCK_SEED, useValue: TEST_SEED },
        { provide: IDENTITY_SERVICE, useValue: identityStub },
      ],
    });

    service = TestBed.inject(ProposalApiServiceMock);
  });

  it('returns seeded proposals on list', async () => {
    const page = await firstValueFrom(service.listProposals());
    expect(page.totalElements).toBeGreaterThan(0);
    expect(page.content.length).toBeGreaterThan(0);
  });

  it('returns a proposal detail by id', async () => {
    const p = await firstValueFrom(service.getProposal('prop-1'));
    expect(p.id).toBe('prop-1');
    expect(p.status).toBe('SUBMITTED');
  });

  it('stores complete requested-object snapshots on editable proposals', async () => {
    const updated = await firstValueFrom(
      service.addRequestedObjects('prop-1', {
        objects: [
          {
            inventoryNumber: 'MNHN-OST-00108',
            displayTitle: 'Lynx pardinus skull',
            objectName: 'Osteological specimen',
            briefDescriptionSnapshot: 'Adult Iberian lynx skull.',
            category: 'osteology',
            description: 'Selected by staff from the simulated catalog search.',
          },
        ],
      }),
    );

    expect(updated.requestedObjects.at(-1)).toMatchObject({
      objectReference: {
        inventoryNumber: 'MNHN-OST-00108',
        displayTitle: 'Lynx pardinus skull',
        objectName: 'Osteological specimen',
        briefDescriptionSnapshot: 'Adult Iberian lynx skull.',
      },
      category: 'osteology',
      description: 'Selected by staff from the simulated catalog search.',
    });
  });

  it('rejects requested objects for terminal proposals', async () => {
    await expect(
      firstValueFrom(
        service.addRequestedObjects('prop-3', {
          objects: [
            {
              inventoryNumber: 'MNHN-MAM-00421',
              displayTitle: 'Lynx pardinus study skin',
              objectName: 'Zoological study skin',
            },
          ],
        }),
      ),
    ).rejects.toMatchObject({ status: 409, error: 'INVALID_TRANSITION' });
  });

  it('partially updates editable metadata without recording an event', async () => {
    const eventsBefore = await firstValueFrom(service.listEvents('prop-1'));

    const result = await firstValueFrom(
      service.updateProposal('prop-1', {
        title: null,
        intendedUse: {
          useType: 'EXHIBITION',
          description: 'Public exhibition of zoology catalogues.',
        },
        endDate: null,
      }),
    );

    expect(result).toMatchObject({
      id: 'prop-1',
      title: null,
      status: 'SUBMITTED',
      endDate: null,
    });

    const updated = await firstValueFrom(service.getProposal('prop-1'));
    expect(updated.title).toBeNull();
    expect(updated.type).toBe('EXHIBITION');
    expect(updated.intendedUse).toEqual({
      useType: 'EXHIBITION',
      description: 'Public exhibition of zoology catalogues.',
    });
    expect(updated.beginDate).toBe('2026-06-01');
    expect(updated.endDate).toBeNull();

    const eventsAfter = await firstValueFrom(service.listEvents('prop-1'));
    expect(eventsAfter.content).toEqual(eventsBefore.content);

    const searchResult = await firstValueFrom(
      service.listProposals({ search: 'VRP-20260601-0001' }),
    );
    expect(searchResult.content.map((proposal) => proposal.id)).toContain('prop-1');
  });

  it('validates the effective date range when one date is omitted', async () => {
    await expect(
      firstValueFrom(service.updateProposal('prop-1', { beginDate: '2027-01-01' })),
    ).rejects.toMatchObject({
      status: 422,
      error: 'INVALID_DATE_RANGE',
    });
  });

  it('refuses updates for terminal proposals and non-staff callers', async () => {
    await expect(
      firstValueFrom(service.updateProposal('prop-4', { title: 'Changed' })),
    ).rejects.toMatchObject({
      status: 409,
      error: 'INVALID_TRANSITION',
    });

    isStaffState.set(false);
    await expect(
      firstValueFrom(service.updateProposal('prop-1', { title: 'Changed' })),
    ).rejects.toMatchObject({
      status: 403,
      error: 'INSUFFICIENT_GROUP',
    });
  });

  it('returns not found when updating an unknown proposal', async () => {
    await expect(
      firstValueFrom(service.updateProposal('missing-proposal', { title: 'Changed' })),
    ).rejects.toMatchObject({
      status: 404,
      error: 'PROPOSAL_NOT_FOUND',
    });
  });

  it('starts seeded proposal conversations with the collection-use request', async () => {
    const [proposal, conversation] = await Promise.all([
      firstValueFrom(service.getProposal('prop-1')),
      firstValueFrom(service.getConversation('prop-1')),
    ]);

    expect(conversation.messages).toHaveLength(1);
    expect(conversation.messages[0]).toMatchObject({
      id: 'msg-prop-1-initial',
      sender: 'alice@ext.example.com',
      recipient: 'collections@vitarerum.example.com',
      subject: 'Collection use request: VR-2026-001',
    });
    expect(conversation.messages[0].body).toContain('zoology specimen catalogues');
    expect(conversation.messages[0].attachments).toEqual([
      {
        documentId: 'doc-prop-1-research-outline',
        fileName: 'zoology-research-outline.pdf',
      },
      {
        documentId: 'doc-prop-1-catalogue-list',
        fileName: 'atlantic-forest-catalogue-list.xlsx',
      },
    ]);
    expect(proposal.documents.map((document) => document.id)).toEqual(
      expect.arrayContaining(['doc-prop-1-research-outline', 'doc-prop-1-catalogue-list']),
    );
  });

  it('includes incoming requester attachments for seeded exhibition proposals', async () => {
    const [proposal, conversation] = await Promise.all([
      firstValueFrom(service.getProposal('prop-4')),
      firstValueFrom(service.getConversation('prop-4')),
    ]);

    expect(conversation.messages).toHaveLength(1);
    expect(conversation.messages[0]).toMatchObject({
      id: 'msg-prop-4-initial',
      sender: 'alice@ext.example.com',
      subject: 'Collection use request: VR-2026-004',
    });
    expect(conversation.messages[0].attachments).toEqual([
      {
        documentId: 'doc-prop-4-exhibition-brief',
        fileName: 'laboratory-instruments-exhibition-brief.pdf',
      },
      {
        documentId: 'doc-prop-4-object-list',
        fileName: 'laboratory-instruments-object-list.csv',
      },
    ]);
    expect(proposal.documents.map((document) => document.id)).toEqual(
      expect.arrayContaining(['doc-prop-4-exhibition-brief', 'doc-prop-4-object-list']),
    );
  });

  it('transitions to APPROVED and updates event log', async () => {
    const result = await firstValueFrom(
      service.approveProposal('prop-3', {
        title: 'T',
        purpose: 'P',
        beginDate: '2026-06-01',
        endDate: '2026-06-30',
        note: 'Looks good',
      }),
    );
    expect(result.proposal.status).toBe('APPROVED');
    expect(result.collectionUseProject?.status).toBe('CREATED');

    const events = await firstValueFrom(service.listEvents('prop-3'));
    const last = events.content[events.content.length - 1];
    expect(last.type).toBe('APPROVED');
  });

  it('propagates proposal APPROVED status to the associated project', async () => {
    const projectService = TestBed.inject(ProjectApiServiceMock);

    await firstValueFrom(
      service.approveProposal('prop-3', {
        title: 'T',
        purpose: 'P',
        beginDate: '2026-06-01',
        endDate: '2026-06-30',
        note: 'Looks good',
      }),
    );

    const project = await firstValueFrom(projectService.getProject('proj-3'));
    expect(project).toMatchObject({
      id: 'proj-3',
      proposal: { id: 'prop-3', status: 'APPROVED' },
    });
  });

  it('cancels a proposal, records a CANCELLED event and cascades the project', async () => {
    const projectService = TestBed.inject(ProjectApiServiceMock);
    await firstValueFrom(
      service.approveProposal('prop-3', {
        title: 'T',
        purpose: 'P',
        beginDate: '2026-06-01',
        endDate: '2026-06-30',
        note: 'Approved',
      }),
    );

    const result = await firstValueFrom(
      service.cancelProposal('prop-3', { reason: 'Trip cancelled' }),
    );
    expect(result.proposal.status).toBe('CANCELLED');
    expect(result.proposal.lastEvent.note).toBe('Trip cancelled');
    expect(result.collectionUseProject?.status).toBe('CANCELLED');

    const proposal = await firstValueFrom(service.getProposal('prop-3'));
    expect(proposal.status).toBe('CANCELLED');

    const events = await firstValueFrom(service.listEvents('prop-3'));
    expect(events.content[events.content.length - 1].type).toBe('CANCELLED');

    const project = await firstValueFrom(projectService.getProject('proj-3'));
    expect(project.status).toBe('CANCELLED');
  });

  it('refuses to cancel a rejected proposal', async () => {
    await firstValueFrom(service.rejectProposal('prop-3', { reason: 'Out of scope' }));

    await expect(
      firstValueFrom(service.cancelProposal('prop-3', { reason: 'Too late' })),
    ).rejects.toMatchObject({ status: 422 });
  });

  it('creates a new proposal and lists it', async () => {
    const created = await firstValueFrom(
      service.createProposal({
        title: 'New study',
        intendedUse: { useType: 'IN_SITU_VISIT', description: 'Test' },
        purpose: 'Test',
        beginDate: '2026-07-01',
        endDate: '2026-12-31',
      }),
    );
    expect(created.proposal.status).toBe('SUBMITTED');
    expect(created.proposal).not.toHaveProperty('collectionUseProject');

    const detail = await firstValueFrom(service.getProposal(created.proposal.id));
    expect(detail.collectionUseProject).toBeUndefined();

    const page = await firstValueFrom(service.listProposals());
    const found = page.content.find((p) => p.id === created.proposal.id);
    expect(found).toBeDefined();
    expect(found?.collectionUseProject).toBeUndefined();
  });

  it('materializes a project only when a new proposal is approved', async () => {
    const projectService = TestBed.inject(ProjectApiServiceMock);
    const created = await firstValueFrom(
      service.createProposal({
        title: 'New study',
        intendedUse: { useType: 'IN_SITU_VISIT', description: 'Test' },
        purpose: 'Test',
        beginDate: '2026-07-01',
        endDate: '2026-12-31',
      }),
    );

    const result = await firstValueFrom(
      service.approveProposal(created.proposal.id, {
        title: 'Approved project',
        purpose: 'Approved purpose',
        beginDate: '2026-08-01',
        endDate: '2026-09-30',
        note: 'Approved',
      }),
    );

    expect(result.collectionUseProject).toMatchObject({
      title: 'Approved project',
      status: 'CREATED',
    });
    const projectSummary = result.collectionUseProject;
    expect(projectSummary).not.toBeNull();

    const detail = await firstValueFrom(service.getProposal(created.proposal.id));
    expect(detail.collectionUseProject).toEqual(projectSummary);

    if (!projectSummary) throw new Error('Expected approved proposal to materialize a project');
    const project = await firstValueFrom(projectService.getProject(projectSummary.id));
    expect(project).toMatchObject({
      title: 'Approved project',
      purpose: 'Approved purpose',
      status: 'CREATED',
      proposal: { id: created.proposal.id, status: 'APPROVED' },
    });
  });

  it('rejects a new pre-approval proposal without a project', async () => {
    const created = await firstValueFrom(
      service.createProposal({
        title: 'Rejected study',
        intendedUse: { useType: 'OTHER', description: 'Test' },
        purpose: 'Test',
        beginDate: '2026-07-01',
        endDate: '2026-12-31',
      }),
    );

    const result = await firstValueFrom(
      service.rejectProposal(created.proposal.id, { reason: 'Out of scope' }),
    );

    expect(result.proposal.status).toBe('REJECTED');
    expect(result.collectionUseProject).toBeNull();

    const detail = await firstValueFrom(service.getProposal(created.proposal.id));
    expect(detail.status).toBe('REJECTED');
    expect(detail.collectionUseProject).toBeUndefined();
  });

  it('seeds the opening message once from the initialMessage fields (Business Rule 01)', async () => {
    const created = await firstValueFrom(
      service.createProposal({
        title: 'New study',
        intendedUse: { useType: 'IN_SITU_VISIT', description: 'Test' },
        purpose: 'Test',
        beginDate: '2026-07-01',
        endDate: '2026-12-31',
        initialMessageRecipient: 'collections@vitarerum.example.com',
        initialMessageSubject: 'Collection use request: new study',
        initialMessageBody: 'Requesting access for a new comparative study.',
      }),
    );

    const conversation = await firstValueFrom(service.getConversation(created.proposal.id));

    expect(conversation.messages).toHaveLength(1);
    expect(conversation.messages[0]).toMatchObject({
      recipient: 'collections@vitarerum.example.com',
      subject: 'Collection use request: new study',
      body: 'Requesting access for a new comparative study.',
    });
  });

  it('creates proposals from opening message fields without proposal details', async () => {
    const created = await firstValueFrom(
      service.createProposal({
        initialMessageRecipient: 'collections@vitarerum.example.com',
        initialMessageSubject: 'Archive access request',
        initialMessageBody: 'I would like to discuss access to archive materials.',
      }),
    );

    const detail = await firstValueFrom(service.getProposal(created.proposal.id));
    const conversation = await firstValueFrom(service.getConversation(created.proposal.id));

    expect(detail).toMatchObject({
      title: 'Archive access request',
      type: 'OTHER',
      intendedUse: {
        useType: 'OTHER',
        description: 'I would like to discuss access to archive materials.',
      },
    });
    expect(detail.beginDate).toBeUndefined();
    expect(detail.endDate).toBeUndefined();
    expect(conversation.messages).toHaveLength(1);
    expect(conversation.messages[0]).toMatchObject({
      recipient: 'collections@vitarerum.example.com',
      subject: 'Archive access request',
      body: 'I would like to discuss access to archive materials.',
    });
  });

  it('falls back to title/purpose when initialMessage fields are omitted', async () => {
    const created = await firstValueFrom(
      service.createProposal({
        title: 'Fallback study',
        intendedUse: { useType: 'IN_SITU_VISIT', description: 'Fallback purpose text' },
        purpose: 'Fallback purpose text',
        beginDate: '2026-07-01',
        endDate: '2026-12-31',
      }),
    );

    const conversation = await firstValueFrom(service.getConversation(created.proposal.id));

    expect(conversation.messages).toHaveLength(1);
    expect(conversation.messages[0]).toMatchObject({
      recipient: 'collections@vitarerum.example.com',
      subject: 'Fallback study',
      body: 'Fallback purpose text',
    });
  });

  it('filters proposals by status', async () => {
    const page = await firstValueFrom(service.listProposals({ status: 'SUBMITTED' }));
    expect(page.content.every((p) => p.status === 'SUBMITTED')).toBe(true);
  });

  it('filters proposals by multiple statuses using OR semantics', async () => {
    const page = await firstValueFrom(service.listProposals({ status: ['REJECTED', 'CANCELLED'] }));

    expect(page.content.length).toBeGreaterThan(0);
    expect(page.content.every((p) => p.status === 'REJECTED' || p.status === 'CANCELLED')).toBe(
      true,
    );
  });

  it('filters proposals by requester permission', async () => {
    const page = await firstValueFrom(service.listProposals({ requestedBy: 'perm-alice' }));
    expect(page.content.length).toBeGreaterThan(0);
    expect(page.content.every((p) => p.requestedBy.permissionId === 'perm-alice')).toBe(true);
  });

  it('SUBMITTED list contains only unassigned proposals', async () => {
    const page = await firstValueFrom(service.listProposals({ status: 'SUBMITTED' }));
    expect(page.content.length).toBeGreaterThan(0);
    expect(page.content.every((p) => p.assignedTo === null)).toBe(true);
    expect(page.content.every((p) => p.status === 'SUBMITTED')).toBe(true);
  });

  it('filters proposals by status', async () => {
    await firstValueFrom(service.assignProposal('prop-1', { note: 'Assuming' }));
    await firstValueFrom(
      service.approveProposal('prop-2', {
        title: 'T',
        purpose: 'P',
        beginDate: '2026-06-01',
        endDate: '2026-06-30',
        note: 'Approved',
      }),
    );

    const pending = await firstValueFrom(service.listProposals({ status: 'PENDING' }));
    const approved = await firstValueFrom(service.listProposals({ status: 'APPROVED' }));

    expect(pending.content.map((proposal) => proposal.id)).toContain('prop-1');
    expect(pending.content.map((proposal) => proposal.id)).not.toContain('prop-2');
    expect(approved.content.map((proposal) => proposal.id)).toContain('prop-2');
  });

  it('assume moves proposal into review and sets assignedTo', async () => {
    const result = await firstValueFrom(service.assignProposal('prop-1', { note: 'Assuming' }));
    expect(result.status).toBe('PENDING');
    expect(result.lastEvent.type).toBe('ASSIGNED');
    expect(result.assignedTo.permissionId).toBe('perm-bob');

    const updated = await firstValueFrom(service.getProposal('prop-1'));
    expect(updated.status).toBe('PENDING');
    expect(updated.assignedTo?.permissionId).toBe('perm-bob');
  });

  it('assumes proposals with the currently logged user permission', async () => {
    sessionState.set({
      accessToken: 'mock-token',
      user: {
        id: 'u-carol',
        email: 'carol@curatorial.example.com',
        displayName: 'Carol Souza',
      },
      group: 'CURATORIAL',
      availableGroups: ['CURATORIAL'],
    });

    const result = await firstValueFrom(service.assignProposal('prop-1', { note: 'Assuming' }));

    expect(result.assignedTo.permissionId).toBe('perm-carol');

    const page = await firstValueFrom(service.listProposals({ assignedTo: 'perm-carol' }));

    expect(page.content.find((p) => p.id === 'prop-1')).toBeDefined();
  });

  it('assume removes proposal from the unassigned-SUBMITTED list', async () => {
    await firstValueFrom(service.assignProposal('prop-1', { note: '' }));

    const page = await firstValueFrom(service.listProposals({ status: 'SUBMITTED' }));
    expect(page.content.find((p) => p.id === 'prop-1')).toBeUndefined();
  });

  it('assigning a target permission moves proposal into review', async () => {
    const result = await firstValueFrom(
      service.assignProposal('prop-1', {
        targetPermissionId: 'perm-carol',
        note: 'Assigning to carol',
      }),
    );
    expect(result.status).toBe('PENDING');
    expect(result.lastEvent.type).toBe('ASSIGNED');
    expect(result.assignedTo.permissionId).toBe('perm-carol');
  });

  it('forwards to multi-group staff permissions from mock users without changing status', async () => {
    const result = await firstValueFrom(
      service.forwardProposal('prop-1', {
        targetPermissionId: 'perm-fran-curatorial',
        note: 'Forwarding to fran',
      }),
    );

    expect(result.status).toBe('SUBMITTED');
    expect(result.assignedTo).toMatchObject({
      permissionId: 'perm-fran-curatorial',
      group: 'CURATORIAL',
      user: {
        id: 'u-fran',
        email: 'fran@staff.example.com',
      },
    });
  });

  it('syncs PENDING proposal status to the associated project on assume', async () => {
    const projectService = TestBed.inject(ProjectApiServiceMock);

    await firstValueFrom(service.assignProposal('prop-1', { note: '' }));

    const project = await firstValueFrom(projectService.getProject('proj-1'));
    expect(project.proposal.status).toBe('PENDING');
  });

  it('propagates proposal REJECTED status to the associated project and cancels it', async () => {
    const projectService = TestBed.inject(ProjectApiServiceMock);

    await firstValueFrom(service.rejectProposal('prop-2', { reason: 'Not viable' }));

    const project = await firstValueFrom(projectService.getProject('proj-2'));
    expect(project.proposal.status).toBe('REJECTED');
    expect(project.status).toBe('CANCELLED');

    const events = await firstValueFrom(projectService.listEvents('proj-2'));
    expect(events.content.at(-1)?.type).toBe('CANCELLED');
  });
});
