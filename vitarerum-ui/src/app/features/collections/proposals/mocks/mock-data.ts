import { inject, Injectable, InjectionToken } from '@angular/core';
import { Group } from '@core/auth/models/group.model';
import { GroupMembership, PermissionPrincipal } from '@core/auth/models/permission.model';
import { UserDetail } from '@core/auth/models/user.model';
import { Page, PageQuery } from '@shared/models/page.model';
import { ProposalStatus } from '@shared/models/collection-use-status.model';

import { ApproveProposalRequest } from '../models/proposal-actions.model';
import {
  ObjectAccessLog,
  ObjectLogEntry,
  ObjectOccurrenceEntry,
  ObjectOccurrenceLog,
  PublicationLog,
  PublicationLogEntry,
  UseEvent,
} from '@features/collections/projects/models/project.model';
import {
  Message,
  ProposalDetail,
  ProposalEvent,
  ProposalProjectSummary,
} from '../models/proposal.model';

export const MOCK_GROUPS: Group[] = [
  { id: 'g-external', name: 'EXTERNAL' },
  { id: 'g-collections', name: 'COLLECTIONS_MANAGEMENT' },
  { id: 'g-curatorial', name: 'CURATORIAL' },
  { id: 'g-direction', name: 'DIRECTION' },
  { id: 'g-admin', name: 'SYS_ADMIN' },
];

export const MOCK_USERS: UserDetail[] = [
  {
    id: 'u-alice',
    name: 'Alice Ferreira',
    email: 'alice@ext.example.com',
    permissions: [{ permissionId: 'perm-alice', group: MOCK_GROUPS[0] }],
  },
  {
    id: 'u-bob',
    name: 'Bob Santos',
    email: 'bob@collections.example.com',
    permissions: [{ permissionId: 'perm-bob', group: MOCK_GROUPS[1] }],
  },
  {
    id: 'u-carol',
    name: 'Carol Souza',
    email: 'carol@curatorial.example.com',
    permissions: [{ permissionId: 'perm-carol', group: MOCK_GROUPS[2] }],
  },
  {
    id: 'u-dan',
    name: 'Dan Oliveira',
    email: 'dan@direction.example.com',
    permissions: [{ permissionId: 'perm-dan', group: MOCK_GROUPS[3] }],
  },
  {
    id: 'u-eve',
    name: 'Eve Lima',
    email: 'eve@admin.example.com',
    permissions: [{ permissionId: 'perm-eve', group: MOCK_GROUPS[4] }],
  },
  {
    id: 'u-fran',
    name: 'Fran Costa',
    email: 'fran@staff.example.com',
    permissions: [
      { permissionId: 'perm-fran-collections', group: MOCK_GROUPS[1] },
      { permissionId: 'perm-fran-curatorial', group: MOCK_GROUPS[2] },
      { permissionId: 'perm-fran-direction', group: MOCK_GROUPS[3] },
    ],
  },
  {
    id: 'u-greg',
    name: 'Greg Viana',
    email: 'greg@collections.example.com',
    permissions: [{ permissionId: 'perm-greg', group: MOCK_GROUPS[1] }],
  },
  {
    id: 'u-hugo',
    name: 'Hugo Andrade',
    email: 'hugo@research.example.com',
    permissions: [{ permissionId: 'perm-hugo', group: MOCK_GROUPS[0] }],
  },
  {
    id: 'u-iris',
    name: 'Iris Nakamura',
    email: 'iris@institute.example.com',
    permissions: [{ permissionId: 'perm-iris', group: MOCK_GROUPS[0] }],
  },
];

export const MOCK_MEMBERSHIPS: GroupMembership[] = [
  { permissionId: 'perm-alice', user: MOCK_USERS[0], group: MOCK_GROUPS[0] },
  { permissionId: 'perm-bob', user: MOCK_USERS[1], group: MOCK_GROUPS[1] },
  { permissionId: 'perm-carol', user: MOCK_USERS[2], group: MOCK_GROUPS[2] },
  { permissionId: 'perm-dan', user: MOCK_USERS[3], group: MOCK_GROUPS[3] },
  { permissionId: 'perm-eve', user: MOCK_USERS[4], group: MOCK_GROUPS[4] },
  { permissionId: 'perm-fran-collections', user: MOCK_USERS[5], group: MOCK_GROUPS[1] },
  { permissionId: 'perm-fran-curatorial', user: MOCK_USERS[5], group: MOCK_GROUPS[2] },
  { permissionId: 'perm-fran-direction', user: MOCK_USERS[5], group: MOCK_GROUPS[3] },
  { permissionId: 'perm-greg', user: MOCK_USERS[6], group: MOCK_GROUPS[1] },
  { permissionId: 'perm-hugo', user: MOCK_USERS[7], group: MOCK_GROUPS[0] },
  { permissionId: 'perm-iris', user: MOCK_USERS[8], group: MOCK_GROUPS[0] },
];

export const P: Record<string, PermissionPrincipal> = {
  alice: {
    permissionId: 'perm-alice',
    user: { id: 'u-alice', name: 'Alice Ferreira', email: 'alice@ext.example.com' },
    group: 'EXTERNAL',
  },
  bob: {
    permissionId: 'perm-bob',
    user: { id: 'u-bob', name: 'Bob Santos', email: 'bob@collections.example.com' },
    group: 'COLLECTIONS_MANAGEMENT',
  },
  carol: {
    permissionId: 'perm-carol',
    user: { id: 'u-carol', name: 'Carol Souza', email: 'carol@curatorial.example.com' },
    group: 'CURATORIAL',
  },
  dan: {
    permissionId: 'perm-dan',
    user: { id: 'u-dan', name: 'Dan Oliveira', email: 'dan@direction.example.com' },
    group: 'DIRECTION',
  },
  eve: {
    permissionId: 'perm-eve',
    user: { id: 'u-eve', name: 'Eve Lima', email: 'eve@admin.example.com' },
    group: 'SYS_ADMIN',
  },
  fran: {
    permissionId: 'perm-fran-collections',
    user: { id: 'u-fran', name: 'Fran Costa', email: 'fran@staff.example.com' },
    group: 'COLLECTIONS_MANAGEMENT',
  },
  greg: {
    permissionId: 'perm-greg',
    user: { id: 'u-greg', name: 'Greg Viana', email: 'greg@collections.example.com' },
    group: 'COLLECTIONS_MANAGEMENT',
  },
  hugo: {
    permissionId: 'perm-hugo',
    user: { id: 'u-hugo', name: 'Hugo Andrade', email: 'hugo@research.example.com' },
    group: 'EXTERNAL',
  },
  iris: {
    permissionId: 'perm-iris',
    user: { id: 'u-iris', name: 'Iris Nakamura', email: 'iris@institute.example.com' },
    group: 'EXTERNAL',
  },
};

export const SEED_PROPOSALS: ProposalDetail[] = [
  // prop-1: SUBMITTED — alice, awaiting first review
  {
    id: 'prop-1',
    referenceNumber: 'VRP-20260601-0001',
    title: 'Zoology specimen catalogues from Atlantic forest surveys',
    status: 'SUBMITTED',
    beginDate: '2026-06-01',
    endDate: '2026-12-31',
    type: 'IN_SITU_VISIT',
    requestedBy: P['alice'],
    assignedTo: null,
    collectionUseProject: {
      id: 'proj-1',
      referenceNumber: 'VR-2026-001',
      title: 'Zoology specimen catalogues from Atlantic forest surveys',
      status: 'CREATED',
    },
    submittedAt: '2026-06-01T09:00:00Z',
    conversationId: 'conv-1',
    intendedUse: {
      useType: 'IN_SITU_VISIT',
      description: 'Research visit to consult specimen catalogues and field records on site.',
    },
    documents: [
      {
        id: 'doc-prop-1-research-outline',
        type: 'REQUESTER_ATTACHMENT',
        fileName: 'zoology-research-outline.pdf',
        fileReference: 'mock-proposal-file/zoology-research-outline.pdf',
        submittedAt: '2026-06-01T09:00:00Z',
        submittedBy: P['alice'],
      },
      {
        id: 'doc-prop-1-catalogue-list',
        type: 'REQUESTER_ATTACHMENT',
        fileName: 'atlantic-forest-catalogue-list.xlsx',
        fileReference: 'mock-proposal-file/atlantic-forest-catalogue-list.xlsx',
        submittedAt: '2026-06-01T09:00:00Z',
        submittedBy: P['alice'],
      },
    ],
    requestedObjects: [],
  },
  // prop-2: PENDING — iris, exhibition, assigned to greg
  {
    id: 'prop-2',
    referenceNumber: 'VRP-20260601-0002',
    title: 'Science history exhibition on botanical illustration',
    status: 'PENDING',
    beginDate: '2026-07-01',
    endDate: '2026-10-15',
    type: 'EXHIBITION',
    requestedBy: P['iris'],
    assignedTo: P['greg'],
    collectionUseProject: {
      id: 'proj-2',
      referenceNumber: 'VR-2026-002',
      title: 'Science history exhibition on botanical illustration',
      status: 'CREATED',
    },
    submittedAt: '2026-06-01T09:30:00Z',
    conversationId: 'conv-2',
    intendedUse: {
      useType: 'EXHIBITION',
      description: 'Public exhibition using botanical illustration materials.',
    },
    documents: [],
    requestedObjects: [],
  },
  // prop-3: APPROVED — hugo, research; fran took it, forwarded to carol; eve watches; project in progress
  {
    id: 'prop-3',
    referenceNumber: 'VRP-20260601-0003',
    title: 'Comparative study of zoological field notebooks',
    status: 'APPROVED',
    beginDate: '2026-06-10',
    endDate: '2027-02-28',
    type: 'IN_SITU_VISIT',
    requestedBy: P['hugo'],
    assignedTo: P['carol'],
    collectionUseProject: {
      id: 'proj-3',
      referenceNumber: 'VR-2026-003',
      title: 'Comparative study of zoological field notebooks',
      status: 'CREATED',
    },
    submittedAt: '2026-06-01T10:00:00Z',
    conversationId: 'conv-3',
    intendedUse: {
      useType: 'IN_SITU_VISIT',
      description: 'Comparative research visit to consult notebooks, sketches, and specimen lists.',
    },
    documents: [],
    requestedObjects: [],
  },
  // prop-4: APPROVED — alice, lab instruments exhibition, bob assigned and approved; project ready to start
  {
    id: 'prop-4',
    referenceNumber: 'VRP-20260601-0004',
    title: 'Science history exhibition on early laboratory instruments',
    status: 'APPROVED',
    beginDate: '2026-08-10',
    endDate: '2027-01-15',
    type: 'EXHIBITION',
    requestedBy: P['alice'],
    assignedTo: P['bob'],
    collectionUseProject: {
      id: 'proj-4',
      referenceNumber: 'VR-2026-004',
      title: 'Science history exhibition on early laboratory instruments',
      status: 'CREATED',
    },
    submittedAt: '2026-06-01T10:30:00Z',
    conversationId: 'conv-4',
    intendedUse: {
      useType: 'EXHIBITION',
      description: 'Public science history exhibition with selected early laboratory instruments.',
    },
    documents: [
      {
        id: 'doc-prop-4-exhibition-brief',
        type: 'REQUESTER_ATTACHMENT',
        fileName: 'laboratory-instruments-exhibition-brief.pdf',
        fileReference: 'mock-proposal-file/laboratory-instruments-exhibition-brief.pdf',
        submittedAt: '2026-06-01T10:30:00Z',
        submittedBy: P['alice'],
      },
      {
        id: 'doc-prop-4-object-list',
        type: 'REQUESTER_ATTACHMENT',
        fileName: 'laboratory-instruments-object-list.csv',
        fileReference: 'mock-proposal-file/laboratory-instruments-object-list.csv',
        submittedAt: '2026-06-01T10:30:00Z',
        submittedBy: P['alice'],
      },
    ],
    requestedObjects: [],
  },
  // prop-5: REJECTED — iris, expedition photography exhibition, greg assigned and rejected
  {
    id: 'prop-5',
    referenceNumber: 'VRP-20260601-0005',
    title: 'Science history exhibition on expedition photography',
    status: 'REJECTED',
    beginDate: '2026-06-15',
    endDate: '2026-09-30',
    type: 'EXHIBITION',
    requestedBy: P['iris'],
    assignedTo: P['greg'],
    collectionUseProject: {
      id: 'proj-5',
      referenceNumber: 'VR-2026-005',
      title: 'Science history exhibition on expedition photography',
      status: 'CANCELLED',
    },
    submittedAt: '2026-06-01T11:00:00Z',
    conversationId: 'conv-5',
    intendedUse: {
      useType: 'EXHIBITION',
      description: 'Public exhibition using expedition photography materials.',
    },
    documents: [],
    requestedObjects: [],
  },
  // prop-6: REJECTED — hugo, botanical herbarium; bob assigned and rejected (scope too broad)
  {
    id: 'prop-6',
    referenceNumber: 'VRP-20260601-0006',
    title: 'Botanical herbarium records of medicinal plant collections',
    status: 'REJECTED',
    beginDate: '2026-07-15',
    endDate: '2027-01-31',
    type: 'IN_SITU_VISIT',
    requestedBy: P['hugo'],
    assignedTo: P['bob'],
    collectionUseProject: {
      id: 'proj-6',
      referenceNumber: 'VR-2026-006',
      title: 'Botanical herbarium records of medicinal plant collections',
      status: 'CANCELLED',
    },
    submittedAt: '2026-06-01T11:30:00Z',
    conversationId: 'conv-6',
    intendedUse: {
      useType: 'IN_SITU_VISIT',
      description: 'Research visit to consult botanical herbarium records.',
    },
    documents: [],
    requestedObjects: [],
  },
  // prop-7: APPROVED — hugo, port photography research; bob forwarded to dan who approved; project completed
  {
    id: 'prop-7',
    referenceNumber: 'VRP-20260601-0007',
    title: 'Photographic history of Rio de Janeiro port, 1890–1930',
    status: 'APPROVED',
    beginDate: '2026-06-01',
    endDate: '2026-06-05',
    type: 'IN_SITU_VISIT',
    requestedBy: P['hugo'],
    assignedTo: P['dan'],
    collectionUseProject: {
      id: 'proj-7',
      referenceNumber: 'VR-2026-007',
      title: 'Photographic history of Rio de Janeiro port, 1890–1930',
      status: 'CREATED',
    },
    submittedAt: '2026-06-01T12:00:00Z',
    conversationId: 'conv-7',
    intendedUse: {
      useType: 'IN_SITU_VISIT',
      description: 'Research access to photographic records for historical study.',
    },
    documents: [],
    requestedObjects: [],
  },
];

export const SEED_PROPOSAL_EVENTS: Record<string, ProposalEvent[]> = {
  'prop-1': [
    { occurredAt: '2026-06-01T09:00:00Z', type: 'SUBMITTED', triggeredBy: P['alice'], note: null },
  ],
  'prop-2': [
    { occurredAt: '2026-06-01T09:30:00Z', type: 'SUBMITTED', triggeredBy: P['iris'], note: null },
    { occurredAt: '2026-06-02T09:00:00Z', type: 'ASSIGNED', triggeredBy: P['greg'], note: null },
  ],
  'prop-3': [
    { occurredAt: '2026-06-01T10:00:00Z', type: 'SUBMITTED', triggeredBy: P['hugo'], note: null },
    { occurredAt: '2026-06-02T09:30:00Z', type: 'ASSIGNED', triggeredBy: P['fran'], note: null },
    {
      occurredAt: '2026-06-02T14:00:00Z',
      type: 'FORWARDED',
      triggeredBy: P['fran'],
      note: 'Forwarding to curatorial for domain review.',
    },
    {
      occurredAt: '2026-06-03T10:00:00Z',
      type: 'APPROVED',
      triggeredBy: P['carol'],
      note: 'Research scope and methodology approved.',
    },
  ],
  'prop-4': [
    { occurredAt: '2026-06-01T10:30:00Z', type: 'SUBMITTED', triggeredBy: P['alice'], note: null },
    { occurredAt: '2026-06-02T10:00:00Z', type: 'ASSIGNED', triggeredBy: P['bob'], note: null },
    {
      occurredAt: '2026-06-03T11:00:00Z',
      type: 'APPROVED',
      triggeredBy: P['bob'],
      note: 'Exhibition scope is clear and feasible.',
    },
  ],
  'prop-5': [
    { occurredAt: '2026-06-01T11:00:00Z', type: 'SUBMITTED', triggeredBy: P['iris'], note: null },
    { occurredAt: '2026-06-02T10:30:00Z', type: 'ASSIGNED', triggeredBy: P['greg'], note: null },
    {
      occurredAt: '2026-06-03T14:00:00Z',
      type: 'REJECTED',
      triggeredBy: P['greg'],
      note: 'The requested photographs are under active conservation review and cannot be used for exhibition at this time.',
    },
  ],
  'prop-6': [
    { occurredAt: '2026-06-01T11:30:00Z', type: 'SUBMITTED', triggeredBy: P['hugo'], note: null },
    { occurredAt: '2026-06-02T11:30:00Z', type: 'ASSIGNED', triggeredBy: P['bob'], note: null },
    {
      occurredAt: '2026-06-03T09:00:00Z',
      type: 'REJECTED',
      triggeredBy: P['bob'],
      note: 'The scope of this request covers material that spans multiple departments and exceeds current access arrangements.',
    },
  ],
  'prop-7': [
    { occurredAt: '2026-06-01T12:00:00Z', type: 'SUBMITTED', triggeredBy: P['hugo'], note: null },
    { occurredAt: '2026-06-02T11:00:00Z', type: 'ASSIGNED', triggeredBy: P['bob'], note: null },
    {
      occurredAt: '2026-06-02T15:00:00Z',
      type: 'FORWARDED',
      triggeredBy: P['bob'],
      note: 'Forwarding to direction for historical assessment.',
    },
    {
      occurredAt: '2026-06-04T10:00:00Z',
      type: 'APPROVED',
      triggeredBy: P['dan'],
      note: 'Historical documentation well justified. Approved.',
    },
  ],
};

export const SEED_MESSAGES: Record<string, Message[]> = {
  'conv-1': [
    {
      id: 'msg-prop-1-initial',
      sentAt: '2026-06-01T09:00:00Z',
      sender: P['alice'].user.email,
      recipient: 'collections@vitarerum.example.com',
      subject: 'Collection use request: VR-2026-001',
      body: 'I am requesting access to the zoology specimen catalogues from Atlantic forest surveys for comparative research on collecting routes and specimen records.',
      attachments: [
        {
          documentId: 'doc-prop-1-research-outline',
          fileName: 'zoology-research-outline.pdf',
        },
        {
          documentId: 'doc-prop-1-catalogue-list',
          fileName: 'atlantic-forest-catalogue-list.xlsx',
        },
      ],
    },
  ],
  'conv-2': [
    {
      id: 'msg-prop-2-initial',
      sentAt: '2026-06-01T09:30:00Z',
      sender: P['iris'].user.email,
      recipient: 'collections@vitarerum.example.com',
      subject: 'Collection use request: VR-2026-002',
      body: 'I am requesting use of botanical illustration materials for a science history exhibition about observation, drawing, and botanical knowledge.',
    },
  ],
  'conv-3': [
    {
      id: 'msg-prop-3-initial',
      sentAt: '2026-06-01T10:00:00Z',
      sender: P['hugo'].user.email,
      recipient: 'collections@vitarerum.example.com',
      subject: 'Collection use request: VR-2026-003',
      body: 'I am requesting access to zoological field notebooks, sketches, and specimen lists for a comparative research study.',
    },
  ],
  'conv-4': [
    {
      id: 'msg-prop-4-initial',
      sentAt: '2026-06-01T10:30:00Z',
      sender: P['alice'].user.email,
      recipient: 'collections@vitarerum.example.com',
      subject: 'Collection use request: VR-2026-004',
      body: 'I am requesting use of early laboratory instrument materials for a science history exhibition about experimental practice and public education.',
      attachments: [
        {
          documentId: 'doc-prop-4-exhibition-brief',
          fileName: 'laboratory-instruments-exhibition-brief.pdf',
        },
        {
          documentId: 'doc-prop-4-object-list',
          fileName: 'laboratory-instruments-object-list.csv',
        },
      ],
    },
  ],
  'conv-5': [
    {
      id: 'msg-prop-5-initial',
      sentAt: '2026-06-01T11:00:00Z',
      sender: P['iris'].user.email,
      recipient: 'collections@vitarerum.example.com',
      subject: 'Collection use request: VR-2026-005',
      body: 'I am requesting use of expedition photography materials for a public science history exhibition on documentation and fieldwork.',
    },
  ],
  'conv-6': [
    {
      id: 'msg-prop-6-initial',
      sentAt: '2026-06-01T11:30:00Z',
      sender: P['hugo'].user.email,
      recipient: 'collections@vitarerum.example.com',
      subject: 'Collection use request: VR-2026-006',
      body: 'I am requesting access to botanical herbarium records of medicinal plant collections for research on classification history and documented uses.',
    },
  ],
  'conv-7': [
    {
      id: 'msg-prop-7-initial',
      sentAt: '2026-06-01T12:00:00Z',
      sender: P['hugo'].user.email,
      recipient: 'collections@vitarerum.example.com',
      subject: 'Collection use request: VR-2026-007',
      body: 'I am requesting access to photographic records documenting the Rio de Janeiro port area between 1890 and 1930.',
    },
  ],
};

export interface MutableProjectState {
  id: string;
  referenceNumber: string;
  title: string;
  purpose: string;
  type: 'EXHIBITION' | 'IN_SITU_VISIT' | 'OTHER';
  status: import('@shared/models/collection-use-status.model').UseStatus;
  result?: import('@shared/models/collection-use-status.model').UseResult | null;
  note?: string | null;
  beginDate: string;
  endDate: string;
  requestedBy: PermissionPrincipal;
  proposalId: string;
  proposalStatus: import('@shared/models/collection-use-status.model').ProposalStatus;
  proposalAssignedTo: PermissionPrincipal | null;
}

export const SEED_PROJECTS: MutableProjectState[] = [
  {
    id: 'proj-1',
    referenceNumber: 'VR-2026-001',
    title: 'Zoology specimen catalogues from Atlantic forest surveys',
    purpose: 'Research comparing zoological specimen catalogues and collecting routes.',
    type: 'IN_SITU_VISIT',
    status: 'CREATED',
    beginDate: '2026-06-01',
    endDate: '2026-12-31',
    requestedBy: P['alice'],
    proposalId: 'prop-1',
    proposalStatus: 'SUBMITTED',
    proposalAssignedTo: null,
  },
  {
    id: 'proj-2',
    referenceNumber: 'VR-2026-002',
    title: 'Science history exhibition on botanical illustration',
    purpose:
      'Selection and display of botanical illustration materials for a science history exhibition.',
    type: 'EXHIBITION',
    status: 'CREATED',
    beginDate: '2026-07-01',
    endDate: '2026-10-15',
    requestedBy: P['iris'],
    proposalId: 'prop-2',
    proposalStatus: 'PENDING',
    proposalAssignedTo: P['greg'],
  },
  {
    id: 'proj-3',
    referenceNumber: 'VR-2026-003',
    title: 'Comparative study of zoological field notebooks',
    purpose: 'Research comparing zoological field notebooks, sketches, and specimen lists.',
    type: 'IN_SITU_VISIT',
    status: 'IN_PROGRESS',
    beginDate: '2026-06-10',
    endDate: '2027-02-28',
    requestedBy: P['hugo'],
    proposalId: 'prop-3',
    proposalStatus: 'APPROVED',
    proposalAssignedTo: P['carol'],
  },
  {
    id: 'proj-4',
    referenceNumber: 'VR-2026-004',
    title: 'Science history exhibition on early laboratory instruments',
    purpose: 'Preparation of early laboratory instruments for a science history exhibition.',
    type: 'EXHIBITION',
    status: 'CREATED',
    beginDate: '2026-08-10',
    endDate: '2027-01-15',
    requestedBy: P['alice'],
    proposalId: 'prop-4',
    proposalStatus: 'APPROVED',
    proposalAssignedTo: P['bob'],
  },
  {
    id: 'proj-5',
    referenceNumber: 'VR-2026-005',
    title: 'Science history exhibition on expedition photography',
    purpose: 'Selection of expedition photographs for a public science history exhibition.',
    type: 'EXHIBITION',
    status: 'CANCELLED',
    result: 'CANCELLED',
    beginDate: '2026-06-15',
    endDate: '2026-09-30',
    requestedBy: P['iris'],
    proposalId: 'prop-5',
    proposalStatus: 'REJECTED',
    proposalAssignedTo: P['greg'],
  },
  {
    id: 'proj-6',
    referenceNumber: 'VR-2026-006',
    title: 'Botanical herbarium records of medicinal plant collections',
    purpose: 'Research on botanical herbarium records and medicinal plant classification.',
    type: 'IN_SITU_VISIT',
    status: 'CANCELLED',
    result: 'CANCELLED',
    beginDate: '2026-07-15',
    endDate: '2027-01-31',
    requestedBy: P['hugo'],
    proposalId: 'prop-6',
    proposalStatus: 'REJECTED',
    proposalAssignedTo: P['bob'],
  },
  {
    id: 'proj-7',
    referenceNumber: 'VR-2026-007',
    title: 'Photographic history of Rio de Janeiro port, 1890–1930',
    purpose: 'Research on photographic records documenting Rio de Janeiro port history.',
    type: 'IN_SITU_VISIT',
    status: 'COMPLETED',
    result: 'COMPLETED',
    beginDate: '2026-06-01',
    endDate: '2026-06-05',
    requestedBy: P['hugo'],
    proposalId: 'prop-7',
    proposalStatus: 'APPROVED',
    proposalAssignedTo: P['dan'],
  },
];

export const SEED_PROJECT_EVENTS: Record<string, UseEvent[]> = {
  'proj-1': [
    { occurredAt: '2026-06-01T09:00:00Z', type: 'REQUESTED', triggeredBy: P['alice'], note: null },
  ],
  'proj-2': [
    { occurredAt: '2026-06-01T09:30:00Z', type: 'REQUESTED', triggeredBy: P['iris'], note: null },
  ],
  'proj-3': [
    { occurredAt: '2026-06-01T10:00:00Z', type: 'REQUESTED', triggeredBy: P['hugo'], note: null },
    {
      occurredAt: '2026-06-03T10:30:00Z',
      type: 'STARTED',
      triggeredBy: P['carol'],
      note: 'Initiating research access.',
    },
  ],
  'proj-4': [
    { occurredAt: '2026-06-01T10:30:00Z', type: 'REQUESTED', triggeredBy: P['alice'], note: null },
  ],
  'proj-5': [
    { occurredAt: '2026-06-01T11:00:00Z', type: 'REQUESTED', triggeredBy: P['iris'], note: null },
    {
      occurredAt: '2026-06-03T14:30:00Z',
      type: 'CANCELLED',
      triggeredBy: P['greg'],
      note: 'Cancelled following rejection of the associated proposal.',
    },
  ],
  'proj-6': [
    { occurredAt: '2026-06-01T11:30:00Z', type: 'REQUESTED', triggeredBy: P['hugo'], note: null },
    {
      occurredAt: '2026-06-03T09:30:00Z',
      type: 'CANCELLED',
      triggeredBy: P['hugo'],
      note: 'Cancelled following withdrawal of the proposal.',
    },
  ],
  'proj-7': [
    { occurredAt: '2026-06-01T12:00:00Z', type: 'REQUESTED', triggeredBy: P['hugo'], note: null },
    { occurredAt: '2026-06-04T10:30:00Z', type: 'STARTED', triggeredBy: P['dan'], note: null },
    {
      occurredAt: '2026-06-05T09:00:00Z',
      type: 'COMPLETED',
      triggeredBy: P['dan'],
      note: 'Research access completed successfully.',
    },
  ],
};

export const SEED_PROJECT_LOG_ENTRIES: Record<string, ObjectLogEntry[]> = {
  'proj-1': [],
  'proj-2': [],
  'proj-3': [
    {
      id: 'entry-101',
      objectReference: {
        inventoryNumber: 'INV-ZOO-1892-001',
        displayTitle: 'Atlantic forest field notebook',
        objectName: 'Field notebook',
        briefDescriptionSnapshot:
          'Zoological field notebook used for Atlantic forest specimen records.',
      },
      numberOfObjects: 1,
      addedAt: '2026-06-04T11:00:00Z',
      addedBy: P['carol'],
      observations: 'Reviewed and compared with specimen records.',
      attachments: [],
    },
    {
      id: 'entry-102',
      objectReference: {
        inventoryNumber: 'INV-ZOO-1892-002',
        displayTitle: 'Field sketch set',
        objectName: 'Sketches',
        briefDescriptionSnapshot: 'Three field sketches cross-referenced with catalogue records.',
      },
      numberOfObjects: 3,
      addedAt: '2026-06-05T09:30:00Z',
      addedBy: P['carol'],
      observations: 'Photographic documentation completed.',
      attachments: [],
    },
  ],
  'proj-4': [],
  'proj-5': [],
  'proj-6': [],
  'proj-7': [],
};

export const SEED_PROJECT_OBJECT_ACCESS_LOGS: Record<string, ObjectAccessLog> = {
  'proj-3': {
    id: 'oal-proj-3',
    referenceNumber: 'OAL-PROJ3',
    projectId: 'proj-3',
    curator: null,
  },
};

export const SEED_PROJECT_OBJECT_OCCURRENCE_LOGS: Record<string, ObjectOccurrenceLog> = {};

export const SEED_PROJECT_OCCURRENCE_ENTRIES: Record<string, ObjectOccurrenceEntry[]> = {
  'proj-1': [],
  'proj-2': [],
  'proj-3': [],
  'proj-4': [],
  'proj-5': [],
  'proj-6': [],
  'proj-7': [],
};

export const SEED_PROJECT_PUBLICATION_LOGS: Record<string, PublicationLog> = {
  'proj-3': {
    id: 'pub-proj-3',
    referenceNumber: 'PUB-PROJ3',
    projectId: 'proj-3',
    curator: null,
  },
};

export const SEED_PROJECT_PUBLICATION_ENTRIES: Record<string, PublicationLogEntry[]> = {
  'proj-3': [
    {
      id: 'pub-entry-101',
      addedAt: '2026-06-10T14:00:00Z',
      addedBy: P['carol'],
      note: 'Published an article in the museum journal.',
      attachments: [],
    },
  ],
};

export const SEED_PROJECT_OBJECTS: Record<string, never[]> = {
  'proj-1': [],
  'proj-2': [],
  'proj-3': [],
  'proj-4': [],
  'proj-5': [],
  'proj-6': [],
  'proj-7': [],
};

export interface MockSeed {
  readonly proposals?: readonly ProposalDetail[];
  readonly proposalEvents?: Record<string, ProposalEvent[]>;
  readonly messages?: Record<string, Message[]>;
  readonly projects?: readonly MutableProjectState[];
  readonly projectEvents?: Record<string, UseEvent[]>;
  readonly objectAccessLogs?: Record<string, ObjectAccessLog>;
  readonly objectOccurrenceLogs?: Record<string, ObjectOccurrenceLog>;
  readonly logEntries?: Record<string, ObjectLogEntry[]>;
  readonly occurrenceEntries?: Record<string, ObjectOccurrenceEntry[]>;
  readonly publicationLogs?: Record<string, PublicationLog>;
  readonly publicationEntries?: Record<string, PublicationLogEntry[]>;
}

export const MOCK_SEED = new InjectionToken<MockSeed>('MOCK_SEED');

export const TEST_SEED: MockSeed = {
  proposals: SEED_PROPOSALS,
  proposalEvents: SEED_PROPOSAL_EVENTS,
  messages: SEED_MESSAGES,
  projects: SEED_PROJECTS,
  projectEvents: SEED_PROJECT_EVENTS,
  objectAccessLogs: SEED_PROJECT_OBJECT_ACCESS_LOGS,
  objectOccurrenceLogs: SEED_PROJECT_OBJECT_OCCURRENCE_LOGS,
  logEntries: SEED_PROJECT_LOG_ENTRIES,
  occurrenceEntries: SEED_PROJECT_OCCURRENCE_ENTRIES,
  publicationLogs: SEED_PROJECT_PUBLICATION_LOGS,
  publicationEntries: SEED_PROJECT_PUBLICATION_ENTRIES,
};

@Injectable()
export class MockProjectState {
  private readonly seed = inject(MOCK_SEED, { optional: true });

  readonly proposals = new Map<string, ProposalDetail>(
    (this.seed?.proposals ?? []).map((p) => [p.id, structuredClone(p)]),
  );
  readonly proposalEvents = new Map<string, ProposalEvent[]>(
    Object.entries(this.seed?.proposalEvents ?? {}).map(([k, v]) => [k, structuredClone(v)]),
  );
  readonly messages = new Map<string, Message[]>(
    Object.entries(this.seed?.messages ?? {}).map(([k, v]) => [k, structuredClone(v)]),
  );
  readonly projects = new Map<string, MutableProjectState>(
    (this.seed?.projects ?? []).map((p) => [p.id, structuredClone(p)]),
  );
  readonly logEntries = new Map<string, ObjectLogEntry[]>(
    Object.entries(this.seed?.logEntries ?? {}).map(([k, v]) => [k, structuredClone(v)]),
  );
  readonly objectAccessLogs = new Map<string, ObjectAccessLog>(
    Object.entries(this.seed?.objectAccessLogs ?? {}).map(([k, v]) => [k, structuredClone(v)]),
  );
  readonly objectOccurrenceLogs = new Map<string, ObjectOccurrenceLog>(
    Object.entries(this.seed?.objectOccurrenceLogs ?? {}).map(([k, v]) => [k, structuredClone(v)]),
  );
  readonly occurrenceEntries = new Map<string, ObjectOccurrenceEntry[]>(
    Object.entries(this.seed?.occurrenceEntries ?? {}).map(([k, v]) => [k, structuredClone(v)]),
  );
  readonly publicationLogs = new Map<string, PublicationLog>(
    Object.entries(this.seed?.publicationLogs ?? {}).map(([k, v]) => [k, structuredClone(v)]),
  );
  readonly publicationEntries = new Map<string, PublicationLogEntry[]>(
    Object.entries(this.seed?.publicationEntries ?? {}).map(([k, v]) => [k, structuredClone(v)]),
  );
  readonly events = new Map<string, UseEvent[]>(
    Object.entries(this.seed?.projectEvents ?? {}).map(([k, v]) => [k, structuredClone(v)]),
  );
  private nextId = 200;

  materializeProjectForProposal(
    proposal: ProposalDetail,
    request: ApproveProposalRequest,
    occurredAt: string,
  ): ProposalProjectSummary & { status: 'CREATED' } {
    const existing = proposal.collectionUseProject;
    const existingProject = existing ? this.projects.get(existing.id) : null;
    const projectId = existing?.id ?? `proj-${proposal.id.replace(/^prop-/, '')}`;
    const referenceNumber =
      existing?.referenceNumber && existing.referenceNumber.trim()
        ? existing.referenceNumber
        : `CUP-${String(this.nextId++).padStart(8, '0')}`;

    const project: MutableProjectState = {
      id: projectId,
      referenceNumber,
      title: request.title,
      purpose: request.purpose,
      type: proposal.type,
      status: existingProject?.status ?? 'CREATED',
      result: existingProject?.result ?? null,
      beginDate: request.beginDate,
      endDate: request.endDate,
      requestedBy: proposal.requestedBy,
      proposalId: proposal.id,
      proposalStatus: 'APPROVED',
      proposalAssignedTo: proposal.assignedTo,
    };
    this.projects.set(project.id, project);
    this.proposals.set(proposal.id, structuredClone(proposal));
    if (!existingProject) {
      this.logEntries.set(project.id, []);
      this.objectAccessLogs.delete(project.id);
      this.occurrenceEntries.set(project.id, []);
      this.objectOccurrenceLogs.delete(project.id);
      this.publicationEntries.set(project.id, []);
      this.publicationLogs.delete(project.id);
      this.events.set(project.id, [
        {
          occurredAt,
          type: 'REQUESTED',
          triggeredBy: proposal.requestedBy,
          note: null,
        },
      ]);
    }

    return {
      id: project.id,
      referenceNumber: project.referenceNumber,
      title: project.title,
      status: 'CREATED',
    };
  }

  syncProposalStatus(
    proposalId: string,
    proposalStatus: ProposalStatus,
    proposalAssignedTo: PermissionPrincipal | null,
    triggeredBy: PermissionPrincipal,
  ): void {
    const project = [...this.projects.values()].find((p) => p.proposalId === proposalId);
    if (!project) return;

    project.proposalStatus = proposalStatus;
    project.proposalAssignedTo = proposalAssignedTo;

    if (proposalStatus === 'REJECTED' || proposalStatus === 'CANCELLED') {
      project.status = 'CANCELLED';
      project.result = 'CANCELLED';
      const events = this.events.get(project.id) ?? [];
      events.push({
        occurredAt: new Date().toISOString(),
        type: 'CANCELLED',
        triggeredBy,
        note: null,
      });
      this.events.set(project.id, events);
    }
  }

  nextEntryId(): string {
    return `entry-${this.nextId++}`;
  }

  nextObjectAccessLogId(): string {
    return `oal-${this.nextId++}`;
  }

  nextObjectAccessLogReference(): string {
    return `OAL-${String(this.nextId++).padStart(8, '0')}`;
  }

  nextObjectOccurrenceLogId(): string {
    return `ool-${this.nextId++}`;
  }

  nextObjectOccurrenceLogReference(): string {
    return `OOL-${String(this.nextId++).padStart(8, '0')}`;
  }

  nextPublicationLogId(): string {
    return `pub-${this.nextId++}`;
  }

  nextPublicationLogReference(): string {
    return `PUB-${String(this.nextId++).padStart(8, '0')}`;
  }

  nextFileReference(): string {
    return `mock-ref-${this.nextId++}`;
  }
}

export function makePageFrom<T>(items: readonly T[], query: PageQuery): Page<T> {
  const page = query.page ?? 0;
  const size = query.size ?? 20;
  const start = page * size;
  return {
    content: items.slice(start, start + size),
    page,
    size,
    totalElements: items.length,
    totalPages: items.length === 0 ? 0 : Math.ceil(items.length / size),
  };
}
