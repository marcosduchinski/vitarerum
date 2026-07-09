import { TestBed } from '@angular/core/testing';
import { HttpErrorResponse } from '@angular/common/http';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';

import { IDENTITY_SERVICE } from '@core/auth/identity.service';
import { IdentityServiceMock } from '@core/auth/identity.service.mock';

import { ResetPasswordComponent } from './reset-password.component';

function fillInput(root: HTMLElement, id: string, value: string): void {
  const input = root.querySelector<HTMLInputElement>(`#${id}`);
  if (!input) throw new Error(`Input #${id} not found`);
  input.value = value;
  input.dispatchEvent(new Event('input'));
}

function configure(identity: IdentityServiceMock, token: string | null) {
  return TestBed.configureTestingModule({
    imports: [ResetPasswordComponent],
    providers: [
      provideRouter([]),
      { provide: IDENTITY_SERVICE, useValue: identity },
      {
        provide: ActivatedRoute,
        useValue: {
          snapshot: {
            queryParamMap: convertToParamMap(token !== null ? { token } : {}),
          },
        },
      },
    ],
  }).compileComponents();
}

describe('ResetPasswordComponent', () => {
  it('shows an invalid-link state and no form when the token is missing', async () => {
    await configure(new IdentityServiceMock(), null);
    const fixture = TestBed.createComponent(ResetPasswordComponent);
    fixture.detectChanges();
    const root = fixture.nativeElement as HTMLElement;

    expect(root.querySelector('form')).toBeNull();
    expect(root.textContent).toContain('missing its reset token');
  });

  it('confirms the reset and shows a success state on a valid token', async () => {
    const identity = new IdentityServiceMock();
    const confirmSpy = vi.spyOn(identity, 'confirmPasswordReset').mockResolvedValue(undefined);
    await configure(identity, 'raw-token');

    const fixture = TestBed.createComponent(ResetPasswordComponent);
    fixture.detectChanges();
    const root = fixture.nativeElement as HTMLElement;

    fillInput(root, 'new-password', 'a-strong-new-password');
    fillInput(root, 'confirm-password', 'a-strong-new-password');
    fixture.detectChanges();

    root.querySelector('form')!.dispatchEvent(new Event('submit'));
    await fixture.whenStable();
    fixture.detectChanges();

    expect(confirmSpy).toHaveBeenCalledWith({
      token: 'raw-token',
      newPassword: 'a-strong-new-password',
    });
    expect(root.textContent).toContain('Password reset. You can now sign in');
  });

  it('signs out any stale local session on success', async () => {
    const identity = new IdentityServiceMock();
    vi.spyOn(identity, 'confirmPasswordReset').mockResolvedValue(undefined);
    const signOutSpy = vi.spyOn(identity, 'signOut');
    await configure(identity, 'raw-token');

    const fixture = TestBed.createComponent(ResetPasswordComponent);
    fixture.detectChanges();
    const root = fixture.nativeElement as HTMLElement;

    fillInput(root, 'new-password', 'a-strong-new-password');
    fillInput(root, 'confirm-password', 'a-strong-new-password');
    fixture.detectChanges();

    root.querySelector('form')!.dispatchEvent(new Event('submit'));
    await fixture.whenStable();
    fixture.detectChanges();

    expect(signOutSpy).toHaveBeenCalledOnce();
  });

  it('shows an opaque invalid/expired/used message on a 404', async () => {
    const identity = new IdentityServiceMock();
    vi.spyOn(identity, 'confirmPasswordReset').mockRejectedValue(
      new HttpErrorResponse({ status: 404 }),
    );
    await configure(identity, 'raw-token');

    const fixture = TestBed.createComponent(ResetPasswordComponent);
    fixture.detectChanges();
    const root = fixture.nativeElement as HTMLElement;

    fillInput(root, 'new-password', 'a-strong-new-password');
    fillInput(root, 'confirm-password', 'a-strong-new-password');
    fixture.detectChanges();

    root.querySelector('form')!.dispatchEvent(new Event('submit'));
    await fixture.whenStable();
    fixture.detectChanges();

    expect(root.textContent).toContain('invalid, expired, or has already been used');
    expect(root.querySelector('a[href="/forgot-password"]')).not.toBeNull();
  });

  it('disables submit until the new password and confirmation match', async () => {
    await configure(new IdentityServiceMock(), 'raw-token');
    const fixture = TestBed.createComponent(ResetPasswordComponent);
    fixture.detectChanges();
    const root = fixture.nativeElement as HTMLElement;

    fillInput(root, 'new-password', 'a-strong-new-password');
    fillInput(root, 'confirm-password', 'does-not-match');
    fixture.detectChanges();

    const submit = root.querySelector<HTMLButtonElement>('button[type="submit"]');
    expect(submit!.disabled).toBe(true);
  });
});
