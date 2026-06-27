import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';

import { IDENTITY_SERVICE } from '@core/auth/identity.service';
import { IdentityServiceMock } from '@core/auth/identity.service.mock';
import { LayoutService } from '@layout/layout.service';

import { AppTopbarComponent } from './app-topbar.component';

class LayoutServiceStub {
  readonly isDarkTheme = signal(false);
  onMenuToggle(): void {
    void this.isDarkTheme();
  }
  toggleDarkMode(): void {
    this.isDarkTheme.update((value) => !value);
  }
}

describe('AppTopbarComponent role switcher', () => {
  let identity: IdentityServiceMock;

  beforeEach(async () => {
    identity = new IdentityServiceMock();

    await TestBed.configureTestingModule({
      imports: [AppTopbarComponent],
      providers: [
        provideRouter([]),
        { provide: IDENTITY_SERVICE, useValue: identity },
        { provide: LayoutService, useClass: LayoutServiceStub },
      ],
    }).compileComponents();
  });

  it('shows the switcher only for multi-group accounts', async () => {
    await identity.signIn({ email: 'bob@collections.example.com', password: 'vita2026' });
    const fixture = TestBed.createComponent(AppTopbarComponent);
    fixture.detectChanges();

    expect(
      (fixture.nativeElement as HTMLElement).querySelector('#role-switcher'),
    ).toBeNull();
  });

  it('switches the active group and permission before navigating to the dashboard', async () => {
    await identity.signIn({ email: 'fran@staff.example.com', password: 'vita2026' });
    const router = TestBed.inject(Router);
    const navigateSpy = vi.spyOn(router, 'navigateByUrl').mockImplementation(async () => {
      expect(identity.session()!.group).toBe('CURATORIAL');
      expect(identity.getPermissionId()).toBe('perm-fran-curatorial');
      return true;
    });

    const fixture = TestBed.createComponent(AppTopbarComponent);
    fixture.detectChanges();

    const select = (fixture.nativeElement as HTMLElement).querySelector<HTMLSelectElement>(
      '#role-switcher',
    );

    expect(select).not.toBeNull();
    expect(select!.options.length).toBe(3);
    expect(identity.session()!.group).toBe('COLLECTIONS_MANAGEMENT');

    select!.value = 'CURATORIAL';
    select!.dispatchEvent(new Event('change'));
    fixture.detectChanges();

    expect(identity.session()!.group).toBe('CURATORIAL');
    expect(identity.getPermissionId()).toBe('perm-fran-curatorial');
    expect(select!.value).toBe('CURATORIAL');
    expect(navigateSpy).toHaveBeenCalledOnce();
    expect(navigateSpy).toHaveBeenCalledWith('/p/dashboard');
  });
});
