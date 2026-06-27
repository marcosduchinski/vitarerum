import {
  getProposalStatusPresentation,
  getUseStatusPresentation,
} from './collection-use-status.model';

describe('collection-use status presentation', () => {
  it('maps proposal statuses to stable labels and tones', () => {
    expect(getProposalStatusPresentation('SUBMITTED')).toEqual({
      label: 'Submitted',
      tone: 'submitted',
    });
    expect(getProposalStatusPresentation('PENDING')).toEqual({
      label: 'Under review',
      tone: 'review',
    });
    expect(getProposalStatusPresentation('REJECTED')).toEqual({
      label: 'Rejected',
      tone: 'rejected',
    });
  });

  it('maps project statuses to stable labels and tones', () => {
    expect(getUseStatusPresentation('CREATED')).toEqual({
      label: 'Created',
      tone: 'submitted',
    });
    expect(getUseStatusPresentation('IN_PROGRESS')).toEqual({
      label: 'In progress',
      tone: 'review',
    });
    expect(getUseStatusPresentation('COMPLETED')).toEqual({
      label: 'Completed',
      tone: 'approved',
    });
    expect(getUseStatusPresentation('CANCELLED')).toEqual({
      label: 'Cancelled',
      tone: 'cancelled',
    });
  });
});
