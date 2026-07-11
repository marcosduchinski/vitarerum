import { ComponentFixture, TestBed } from '@angular/core/testing';

import { RequestedObject } from '../../models/proposal.model';
import { ProposalObjectsSectionComponent } from './proposal-objects-section.component';

const REQUESTED_OBJECT: RequestedObject = {
  id: 'requested-object-1',
  objectReference: {
    inventoryNumber: 'INV-001',
    displayTitle: 'Book of Hours',
    objectName: 'Illuminated manuscript',
    briefDescriptionSnapshot: 'Decorated manuscript snapshot.',
  },
  category: 'manuscript',
  description: 'Requested for comparative study.',
  requestedAt: '2026-06-01T10:00:00Z',
  requestedBy: {
    permissionId: 'permission-1',
    user: { id: 'user-1', name: 'Alice Ferreira', email: 'alice@example.test' },
    group: 'EXTERNAL',
  },
};

describe('ProposalObjectsSectionComponent', () => {
  let fixture: ComponentFixture<ProposalObjectsSectionComponent>;

  async function setup(objects: RequestedObject[] = [REQUESTED_OBJECT]): Promise<HTMLElement> {
    await TestBed.configureTestingModule({
      imports: [ProposalObjectsSectionComponent],
    }).compileComponents();

    fixture = TestBed.createComponent(ProposalObjectsSectionComponent);
    fixture.componentRef.setInput('objects', objects);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  it('lists requested objects', async () => {
    const el = await setup();

    expect(el.textContent).toContain('Requested objects');
    expect(el.textContent).toContain('INV-001');
    expect(el.textContent).toContain('Book of Hours');
    expect(el.textContent).toContain('Illuminated manuscript');
  });

  it('shows an empty state', async () => {
    const el = await setup([]);

    expect(el.textContent).toContain('No objects have been requested');
  });

  it('confirms before emitting remove requests', async () => {
    const el = await setup();
    const emitted: string[] = [];
    fixture.componentRef.instance.removeRequested.subscribe((id) => emitted.push(id));

    el.querySelector<HTMLButtonElement>('.object__remove')!.click();
    fixture.detectChanges();

    expect(emitted).toEqual([]);
    expect(el.textContent).toContain('Remove requested object?');
    expect(el.textContent).toContain('This will remove Book of Hours from this proposal.');

    const confirmButton = Array.from(el.querySelectorAll<HTMLButtonElement>('button')).find(
      (button) => button.textContent?.trim() === 'Remove object',
    );
    expect(confirmButton).toBeDefined();
    confirmButton!.click();

    expect(emitted).toEqual(['requested-object-1']);
  });

  it('opens the empty add modal', async () => {
    const el = await setup();

    el.querySelector<HTMLButtonElement>('.objects__add')!.click();
    fixture.detectChanges();

    expect(el.querySelector('.add-modal')).not.toBeNull();
    expect(el.textContent).toContain('Add requested object');
  });
});
