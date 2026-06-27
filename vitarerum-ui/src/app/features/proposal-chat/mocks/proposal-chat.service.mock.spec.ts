import { computed, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { firstValueFrom } from 'rxjs';

import { IDENTITY_SERVICE, IdentityService } from '@core/auth/identity.service';
import { GroupName } from '@core/auth/models/group-name.enum';
import { IdentitySession } from '@core/auth/models/identity-session.model';
import { LoginRequest } from '@core/auth/models/login.model';
import { ProjectApiServiceMock } from '@features/collections/projects/mocks/project-api.service.mock';
import {
  MOCK_SEED,
  MockProjectState,
  TEST_SEED,
} from '@features/collections/proposals/mocks/mock-data';
import { ProposalApiServiceMock } from '@features/collections/proposals/mocks/proposal-api.service.mock';
import { PROPOSAL_API_SERVICE } from '@features/collections/proposals/services/proposal-api.service';

import { ProposalChatServiceMock } from './proposal-chat.service.mock';

const staffSession: IdentitySession = {
  accessToken: 'mock-token',
  user: {
    id: 'u-bob',
    email: 'bob@collections.example.com',
    displayName: 'Bob Santos',
  },
  group: 'COLLECTIONS_MANAGEMENT',
  availableGroups: ['COLLECTIONS_MANAGEMENT', 'EXTERNAL'],
  permissions: [
    { permissionId: 'perm-bob', group: 'COLLECTIONS_MANAGEMENT' },
    { permissionId: 'perm-hugo', group: 'EXTERNAL' },
  ],
};

const sessionState = signal<IdentitySession | null>(staffSession);

const identityStub: IdentityService = {
  session: sessionState.asReadonly(),
  isAuthenticated: computed(() => sessionState() !== null),
  isStaff: computed(() => {
    const group = sessionState()?.group;
    return group != null && group !== 'EXTERNAL';
  }),
  signIn: async (credentials: LoginRequest) => {
    const session = sessionState();
    if (session) {
      sessionState.set({ ...session, user: { ...session.user, email: credentials.email } });
    }
  },
  signOut: () => sessionState.set(null),
  getAccessToken: () => sessionState()?.accessToken ?? null,
  getPermissionId: () =>
    sessionState()?.permissions?.find((permission) => permission.group === sessionState()?.group)
      ?.permissionId ?? null,
  setGroup: (group: GroupName) => {
    const session = sessionState();
    if (session) sessionState.set({ ...session, group });
  },
  updateAvailableGroups: (groups: readonly GroupName[]) => {
    const session = sessionState();
    if (session) sessionState.set({ ...session, availableGroups: groups });
  },
};

describe('ProposalChatServiceMock', () => {
  let service: ProposalChatServiceMock;
  let proposalService: ProposalApiServiceMock;

  beforeEach(() => {
    sessionState.set(staffSession);

    TestBed.configureTestingModule({
      providers: [
        ProposalChatServiceMock,
        ProposalApiServiceMock,
        ProjectApiServiceMock,
        MockProjectState,
        { provide: MOCK_SEED, useValue: TEST_SEED },
        { provide: IDENTITY_SERVICE, useValue: identityStub },
        { provide: PROPOSAL_API_SERVICE, useExisting: ProposalApiServiceMock },
      ],
    });

    service = TestBed.inject(ProposalChatServiceMock);
    proposalService = TestBed.inject(ProposalApiServiceMock);
  });

  it('loads ProposalChat context for a focus message', async () => {
    const context = await firstValueFrom(
      service.getContext({
        conversationId: 'conv-4',
        messageId: 'msg-prop-4-initial',
      }),
    );

    expect(context).toMatchObject({
      conversationId: 'conv-4',
      focusMessage: {
        messageId: 'msg-prop-4-initial',
        sender: 'alice@ext.example.com',
        subject: 'Collection use request: VR-2026-004',
      },
      proposal: {
        proposalId: 'prop-4',
        referenceNumber: 'VRP-20260601-0004',
        intendedUse: {
          useType: 'EXHIBITION',
        },
      },
    });
  });

  it('suggests exhibition intended use with float confidence and source provenance', async () => {
    const suggestion = await firstValueFrom(
      service.suggestIntendedUse({
        conversationId: 'conv-4',
        messageId: 'msg-prop-4-initial',
      }),
    );

    expect(suggestion.intendedUse.useType).toBe('EXHIBITION');
    expect(suggestion.confidence).toBeGreaterThan(0);
    expect(suggestion.confidence).toBeLessThanOrEqual(1);
    expect(suggestion.rationale).toContain('exhibition');
    expect(suggestion.source).toEqual({
      conversationId: 'conv-4',
      messageId: 'msg-prop-4-initial',
    });
  });

  it('suggests in-situ visits for research access messages', async () => {
    const suggestion = await firstValueFrom(
      service.suggestIntendedUse({
        conversationId: 'conv-1',
        messageId: 'msg-prop-1-initial',
      }),
    );

    expect(suggestion.intendedUse.useType).toBe('IN_SITU_VISIT');
    expect(suggestion.rationale).toContain('in situ visit');
  });

  it('does not persist events when a suggestion is generated', async () => {
    const before = await firstValueFrom(proposalService.listEvents('prop-4'));

    await firstValueFrom(
      service.suggestIntendedUse({
        conversationId: 'conv-4',
        messageId: 'msg-prop-4-initial',
      }),
    );

    const after = await firstValueFrom(proposalService.listEvents('prop-4'));
    expect(after.content).toEqual(before.content);
  });

  it('rejects empty focus message bodies as domain errors', async () => {
    const created = await firstValueFrom(
      proposalService.createProposal({
        title: 'Blank message triage fixture',
        intendedUse: { useType: 'OTHER', description: 'Unclear' },
        purpose: 'Fallback purpose',
        beginDate: '2026-07-01',
        endDate: '2026-07-31',
        initialMessageBody: '   ',
      }),
    );

    await expect(
      firstValueFrom(
        service.suggestIntendedUse({
          conversationId: created.conversationId,
          messageId: 'msg-101',
        }),
      ),
    ).rejects.toMatchObject({
      status: 422,
      error: 'EMPTY_MESSAGE_BODY',
    });
  });

  it('returns conversation and message not-found errors', async () => {
    await expect(
      firstValueFrom(service.getContext({ conversationId: 'missing-conv', messageId: 'msg-1' })),
    ).rejects.toMatchObject({
      status: 404,
      error: 'CONVERSATION_NOT_FOUND',
    });

    await expect(
      firstValueFrom(service.getContext({ conversationId: 'conv-4', messageId: 'missing-msg' })),
    ).rejects.toMatchObject({
      status: 404,
      error: 'MESSAGE_NOT_FOUND',
    });
  });

  it('restricts ProposalChat to staff users', async () => {
    identityStub.setGroup('EXTERNAL');

    await expect(
      firstValueFrom(
        service.getContext({
          conversationId: 'conv-4',
          messageId: 'msg-prop-4-initial',
        }),
      ),
    ).rejects.toMatchObject({
      status: 403,
      error: 'ACCESS_DENIED',
    });
  });
});
