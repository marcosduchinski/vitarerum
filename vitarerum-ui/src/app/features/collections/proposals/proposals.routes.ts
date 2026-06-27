import { inject } from '@angular/core';
import { ResolveFn, Routes } from '@angular/router';
import { map } from 'rxjs';

import { externalGuard } from '@core/guards/external.guard';
import { staffGuard } from '@core/guards/staff.guard';

import { PROPOSAL_API_SERVICE } from './services/proposal-api.service';

const proposalChatConversationIdResolver: ResolveFn<string> = (route) => {
  const proposalId = route.paramMap.get('id') ?? '';
  return inject(PROPOSAL_API_SERVICE)
    .getProposal(proposalId)
    .pipe(map((proposal) => proposal.conversationId));
};

export const PROPOSALS_ROUTES: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'new' },
  {
    path: 'new',
    title: 'New Proposals',
    canMatch: [staffGuard],
    loadComponent: () =>
      import('./pages/new/proposals-new-page.component').then((m) => m.ProposalsNewPageComponent),
  },
  {
    path: 'submit',
    title: 'Submit Proposal',
    canMatch: [externalGuard],
    loadComponent: () =>
      import('./pages/submit/proposal-submit-page.component').then(
        (m) => m.ProposalSubmitPageComponent,
      ),
  },
  {
    path: 'my',
    title: 'My Proposals',
    loadComponent: () =>
      import('./pages/my/proposals-my-page.component').then((m) => m.ProposalsMyPageComponent),
  },
  {
    path: 'my-assignments',
    title: 'My Assignments',
    canMatch: [staffGuard],
    loadComponent: () =>
      import('./pages/my-assignments/proposals-my-assignments-page.component').then(
        (m) => m.ProposalsMyAssignmentsPageComponent,
      ),
  },
  {
    path: 'my-assignments/:id/assistant/:messageId',
    title: 'ProposalChat',
    canMatch: [staffGuard],
    resolve: {
      conversationId: proposalChatConversationIdResolver,
    },
    loadComponent: () =>
      import('../../proposal-chat/components/proposal-chat-panel/proposal-chat-panel.component').then(
        (m) => m.ProposalChatPanelComponent,
      ),
  },
  {
    path: 'my-assignments/:id/edit',
    title: 'Edit Proposal',
    canMatch: [staffGuard],
    loadComponent: () =>
      import('./pages/edit/proposal-edit-page.component').then((m) => m.ProposalEditPageComponent),
  },
  {
    path: 'my-assignments/:id',
    title: 'My Assignment',
    canMatch: [staffGuard],
    loadComponent: () =>
      import('./pages/my-detail/proposal-my-detail-page.component').then(
        (m) => m.ProposalMyDetailPageComponent,
      ),
  },
  {
    path: 'others',
    title: "Other's Assignments",
    canMatch: [staffGuard],
    loadComponent: () =>
      import('./pages/others/proposals-others-page.component').then(
        (m) => m.ProposalsOthersPageComponent,
      ),
  },
  {
    path: 'others/:id',
    title: 'Assignment',
    canMatch: [staffGuard],
    loadComponent: () =>
      import('./pages/others-detail/proposal-others-detail-page.component').then(
        (m) => m.ProposalOthersDetailPageComponent,
      ),
  },
  {
    path: 'approved',
    title: 'Approved Proposals',
    canMatch: [staffGuard],
    loadComponent: () =>
      import('./pages/approved/proposals-approved-page.component').then(
        (m) => m.ProposalsApprovedPageComponent,
      ),
  },
  {
    path: 'approved/:id',
    title: 'Approved Proposal',
    canMatch: [staffGuard],
    loadComponent: () =>
      import('./pages/approved-detail/proposal-approved-detail-page.component').then(
        (m) => m.ProposalApprovedDetailPageComponent,
      ),
  },
  {
    path: 'rejected',
    title: 'Rejected / Cancelled Proposals',
    canMatch: [staffGuard],
    loadComponent: () =>
      import('./pages/rejected/proposals-rejected-page.component').then(
        (m) => m.ProposalsRejectedPageComponent,
      ),
  },
  {
    path: 'rejected/:id',
    title: 'Rejected Proposal',
    canMatch: [staffGuard],
    loadComponent: () =>
      import('./pages/rejected-detail/proposal-rejected-detail-page.component').then(
        (m) => m.ProposalRejectedDetailPageComponent,
      ),
  },
  {
    // Named segments above take precedence; :id is only reached for actual proposal IDs.
    path: ':id',
    title: 'Proposal',
    loadComponent: () =>
      import('./pages/detail/proposal-detail-page.component').then(
        (m) => m.ProposalDetailPageComponent,
      ),
  },
];
