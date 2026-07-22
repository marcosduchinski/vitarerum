import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { PublicShellComponent } from './public-shell.component';

describe('PublicShellComponent', () => {
  it('links the public brand mark to the login screen', async () => {
    await TestBed.configureTestingModule({
      imports: [PublicShellComponent],
      providers: [provideRouter([])],
    }).compileComponents();

    const fixture = TestBed.createComponent(PublicShellComponent);
    fixture.detectChanges();

    const root = fixture.nativeElement as HTMLElement;
    const brandLink = root.querySelector<HTMLAnchorElement>('.public-shell__brand');

    expect(brandLink?.getAttribute('href')).toBe('/login');
  });
});
