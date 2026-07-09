import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';

import { IDENTITY_SERVICE } from '@core/auth/identity.service';
import { IdentityServiceMock } from '@core/auth/identity.service.mock';
import { USE_MOCK_AUTH } from '@core/config/app-config.model';

import { LoginComponent } from './login.component';

function configure(options: { mockAuth?: boolean; message?: string } = {}) {
  return TestBed.configureTestingModule({
    imports: [LoginComponent],
    providers: [
      provideRouter([]),
      { provide: IDENTITY_SERVICE, useValue: new IdentityServiceMock() },
      { provide: USE_MOCK_AUTH, useValue: options.mockAuth ?? false },
      {
        provide: ActivatedRoute,
        useValue: {
          snapshot: {
            queryParamMap: convertToParamMap(options.message ? { message: options.message } : {}),
          },
        },
      },
    ],
  }).compileComponents();
}

describe('LoginComponent', () => {
  it('does not prefill credentials outside mock mode', async () => {
    await configure({ mockAuth: false });
    const fixture = TestBed.createComponent(LoginComponent);
    fixture.detectChanges();
    const root = fixture.nativeElement as HTMLElement;

    expect(root.querySelector<HTMLInputElement>('#email')!.value).toBe('');
    expect(root.querySelector<HTMLInputElement>('#password')!.value).toBe('');
  });

  it('prefills demo credentials in mock mode', async () => {
    await configure({ mockAuth: true });
    const fixture = TestBed.createComponent(LoginComponent);
    fixture.detectChanges();
    const root = fixture.nativeElement as HTMLElement;

    expect(root.querySelector<HTMLInputElement>('#email')!.value).toBe('alice@ext.example.com');
    expect(root.querySelector<HTMLInputElement>('#password')!.value).toBe('password');
  });

  it('shows no info banner without a message query param', async () => {
    await configure();
    const fixture = TestBed.createComponent(LoginComponent);
    fixture.detectChanges();

    expect((fixture.nativeElement as HTMLElement).querySelector('.login-info')).toBeNull();
  });

  it('shows the password-changed info banner from the message query param', async () => {
    await configure({ message: 'password-changed' });
    const fixture = TestBed.createComponent(LoginComponent);
    fixture.detectChanges();

    expect((fixture.nativeElement as HTMLElement).querySelector('.login-info')?.textContent).toContain(
      'Password changed. Sign in again.',
    );
  });

  it('shows a Forgot password? link to /forgot-password', async () => {
    await configure();
    const fixture = TestBed.createComponent(LoginComponent);
    fixture.detectChanges();
    const root = fixture.nativeElement as HTMLElement;

    const link = root.querySelector<HTMLAnchorElement>('a[href="/forgot-password"]');
    expect(link).not.toBeNull();
    expect(link!.textContent).toContain('Forgot password?');
  });
});
