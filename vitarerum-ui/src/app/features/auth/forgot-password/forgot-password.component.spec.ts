import { TestBed } from '@angular/core/testing';
import { HttpErrorResponse } from '@angular/common/http';
import { provideRouter } from '@angular/router';

import { IDENTITY_SERVICE } from '@core/auth/identity.service';
import { IdentityServiceMock } from '@core/auth/identity.service.mock';

import { ForgotPasswordComponent } from './forgot-password.component';

function fillInput(root: HTMLElement, id: string, value: string): void {
  const input = root.querySelector<HTMLInputElement>(`#${id}`);
  if (!input) throw new Error(`Input #${id} not found`);
  input.value = value;
  input.dispatchEvent(new Event('input'));
}

describe('ForgotPasswordComponent', () => {
  let identity: IdentityServiceMock;

  beforeEach(async () => {
    identity = new IdentityServiceMock();
    await TestBed.configureTestingModule({
      imports: [ForgotPasswordComponent],
      providers: [provideRouter([]), { provide: IDENTITY_SERVICE, useValue: identity }],
    }).compileComponents();
  });

  it('always shows the same generic success message, known or unknown email', async () => {
    const requestSpy = vi.spyOn(identity, 'requestPasswordReset').mockResolvedValue(undefined);

    const fixture = TestBed.createComponent(ForgotPasswordComponent);
    fixture.detectChanges();
    const root = fixture.nativeElement as HTMLElement;

    fillInput(root, 'email', 'anyone@example.com');
    fixture.detectChanges();

    root.querySelector('form')!.dispatchEvent(new Event('submit'));
    await fixture.whenStable();
    fixture.detectChanges();

    expect(requestSpy).toHaveBeenCalledWith({ email: 'anyone@example.com' });
    expect(root.textContent).toContain("we've sent a link to reset the password");
    expect(root.querySelector('form')).toBeNull();
  });

  it('shows an error when the request itself fails (e.g. rate limited)', async () => {
    vi.spyOn(identity, 'requestPasswordReset').mockRejectedValue(
      new HttpErrorResponse({ status: 429 }),
    );

    const fixture = TestBed.createComponent(ForgotPasswordComponent);
    fixture.detectChanges();
    const root = fixture.nativeElement as HTMLElement;

    fillInput(root, 'email', 'anyone@example.com');
    fixture.detectChanges();

    root.querySelector('form')!.dispatchEvent(new Event('submit'));
    await fixture.whenStable();
    fixture.detectChanges();

    expect(root.querySelector('form')).not.toBeNull();
    expect(root.querySelector('app-error-message')).not.toBeNull();
  });

  it('disables submit until the email looks valid', () => {
    const fixture = TestBed.createComponent(ForgotPasswordComponent);
    fixture.detectChanges();
    const root = fixture.nativeElement as HTMLElement;

    fillInput(root, 'email', 'not-an-email');
    fixture.detectChanges();

    const submit = root.querySelector<HTMLButtonElement>('button[type="submit"]');
    expect(submit!.disabled).toBe(true);
  });
});
