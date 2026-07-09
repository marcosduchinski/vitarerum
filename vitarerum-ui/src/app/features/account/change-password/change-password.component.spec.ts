import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';

import { IDENTITY_SERVICE } from '@core/auth/identity.service';
import { IdentityServiceMock } from '@core/auth/identity.service.mock';

import { ChangePasswordComponent } from './change-password.component';

function fillInput(root: HTMLElement, id: string, value: string): void {
  const input = root.querySelector<HTMLInputElement>(`#${id}`);
  if (!input) throw new Error(`Input #${id} not found`);
  input.value = value;
  input.dispatchEvent(new Event('input'));
}

describe('ChangePasswordComponent', () => {
  let identity: IdentityServiceMock;

  beforeEach(async () => {
    identity = new IdentityServiceMock();

    await TestBed.configureTestingModule({
      imports: [ChangePasswordComponent],
      providers: [provideRouter([]), { provide: IDENTITY_SERVICE, useValue: identity }],
    }).compileComponents();
  });

  it('signs out and navigates to /login on success', async () => {
    const changePasswordSpy = vi.spyOn(identity, 'changePassword').mockResolvedValue(undefined);
    const signOutSpy = vi.spyOn(identity, 'signOut');
    const router = TestBed.inject(Router);
    const navigateSpy = vi.spyOn(router, 'navigate').mockResolvedValue(true);

    const fixture = TestBed.createComponent(ChangePasswordComponent);
    fixture.detectChanges();
    const root = fixture.nativeElement as HTMLElement;

    fillInput(root, 'current-password', 'old-password');
    fillInput(root, 'new-password', 'a-strong-new-password');
    fillInput(root, 'confirm-password', 'a-strong-new-password');
    fixture.detectChanges();

    root.querySelector('form')!.dispatchEvent(new Event('submit'));
    await fixture.whenStable();

    expect(changePasswordSpy).toHaveBeenCalledWith({
      currentPassword: 'old-password',
      newPassword: 'a-strong-new-password',
    });
    expect(signOutSpy).toHaveBeenCalledOnce();
    expect(navigateSpy).toHaveBeenCalledWith(['/login'], {
      queryParams: { message: 'password-changed' },
    });
  });

  it('shows an error and does not sign out when the current password is wrong', async () => {
    vi.spyOn(identity, 'changePassword').mockRejectedValue(
      new HttpErrorResponse({ status: 400, error: { message: 'nope' } }),
    );
    const signOutSpy = vi.spyOn(identity, 'signOut');

    const fixture = TestBed.createComponent(ChangePasswordComponent);
    fixture.detectChanges();
    const root = fixture.nativeElement as HTMLElement;

    fillInput(root, 'current-password', 'wrong');
    fillInput(root, 'new-password', 'a-strong-new-password');
    fillInput(root, 'confirm-password', 'a-strong-new-password');
    fixture.detectChanges();

    root.querySelector('form')!.dispatchEvent(new Event('submit'));
    await fixture.whenStable();
    fixture.detectChanges();

    expect(signOutSpy).not.toHaveBeenCalled();
    expect(root.textContent).toContain('Invalid data');
  });

  it('disables submit until the new password and confirmation match', () => {
    const fixture = TestBed.createComponent(ChangePasswordComponent);
    fixture.detectChanges();
    const root = fixture.nativeElement as HTMLElement;

    fillInput(root, 'current-password', 'old-password');
    fillInput(root, 'new-password', 'a-strong-new-password');
    fillInput(root, 'confirm-password', 'does-not-match');
    fixture.detectChanges();

    const submit = root.querySelector<HTMLButtonElement>('button[type="submit"]');
    expect(submit!.disabled).toBe(true);
  });
});
