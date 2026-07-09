import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { USER_MANAGEMENT_SERVICE } from '@features/admin/services/user-management.service';

import { UserNewComponent } from './user-new.component';

function fillInput(root: HTMLElement, id: string, value: string): void {
  const input = root.querySelector<HTMLInputElement>(`#${id}`);
  if (!input) throw new Error(`Input #${id} not found`);
  input.value = value;
  input.dispatchEvent(new Event('input'));
  input.dispatchEvent(new Event('blur'));
}

describe('UserNewComponent', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [UserNewComponent],
      providers: [
        provideRouter([]),
        { provide: USER_MANAGEMENT_SERVICE, useValue: { createUser: vi.fn() } },
      ],
    }).compileComponents();
  });

  it('rejects a password shorter than the shared minimum (12 characters)', () => {
    const fixture = TestBed.createComponent(UserNewComponent);
    fixture.detectChanges();
    const root = fixture.nativeElement as HTMLElement;

    fillInput(root, 'user-name', 'New User');
    fillInput(root, 'user-email', 'new@example.org');
    fillInput(root, 'user-password', 'short-pw');
    fixture.detectChanges();

    const submit = root.querySelector<HTMLButtonElement>('button[type="submit"]');
    expect(submit!.disabled).toBe(true);
    expect(root.textContent).toContain('at least 12 characters');
  });

  it('enables submit once the password satisfies the shared policy', () => {
    const fixture = TestBed.createComponent(UserNewComponent);
    fixture.detectChanges();
    const root = fixture.nativeElement as HTMLElement;

    fillInput(root, 'user-name', 'New User');
    fillInput(root, 'user-email', 'new@example.org');
    fillInput(root, 'user-password', 'a-strong-new-password');
    fixture.detectChanges();

    const submit = root.querySelector<HTMLButtonElement>('button[type="submit"]');
    expect(submit!.disabled).toBe(false);
  });
});
