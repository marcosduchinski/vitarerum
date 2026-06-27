import { ComponentFixture, TestBed } from '@angular/core/testing';
import { MenuItem } from 'primeng/api';

import { RowActionsComponent } from './row-actions.component';

describe('RowActionsComponent', () => {
  async function render(
    items: MenuItem[],
    ariaLabel = 'Row actions',
    disabled = false,
  ): Promise<ComponentFixture<RowActionsComponent>> {
    const fixture = TestBed.createComponent(RowActionsComponent);
    fixture.componentRef.setInput('items', items);
    fixture.componentRef.setInput('ariaLabel', ariaLabel);
    fixture.componentRef.setInput('disabled', disabled);
    fixture.detectChanges();
    await fixture.whenStable();
    return fixture;
  }

  afterEach(() => {
    document.querySelectorAll('.p-menu').forEach((element) => element.remove());
  });

  it('renders an accessible trigger with the provided label', async () => {
    const fixture = await render([{ label: 'Details' }], 'More actions for VR-1');
    const trigger = (fixture.nativeElement as HTMLElement).querySelector<HTMLButtonElement>(
      'button',
    );

    expect(trigger?.getAttribute('aria-label')).toBe('More actions for VR-1');
    expect(trigger?.getAttribute('aria-haspopup')).toBe('menu');
  });

  it('opens the popup with the supplied items and runs the command', async () => {
    const command = vi.fn();
    const fixture = await render([{ label: 'Details' }, { label: 'Cancel', command }]);

    (fixture.nativeElement as HTMLElement).querySelector<HTMLButtonElement>('button')!.click();
    fixture.detectChanges();
    await fixture.whenStable();

    const items = Array.from(
      document.body.querySelectorAll<HTMLElement>('.p-menu a, .p-menu button'),
    );
    expect(items.some((item) => item.textContent?.trim() === 'Details')).toBe(true);

    const cancel = items.find((item) => item.textContent?.trim() === 'Cancel');
    cancel!.click();
    expect(command).toHaveBeenCalled();
  });

  it('disables the trigger when disabled is set', async () => {
    const fixture = await render([{ label: 'Details' }], 'Row actions', true);
    expect(
      (fixture.nativeElement as HTMLElement).querySelector<HTMLButtonElement>('button')!.disabled,
    ).toBe(true);
  });
});
