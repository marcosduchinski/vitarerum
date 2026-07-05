import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { PublicLandingPageComponent } from './public-landing-page.component';

describe('PublicLandingPageComponent', () => {
  it('shows both choices linking to their respective flows', async () => {
    await TestBed.configureTestingModule({
      imports: [PublicLandingPageComponent],
      providers: [provideRouter([])],
    }).compileComponents();

    const fixture = TestBed.createComponent(PublicLandingPageComponent);
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;

    const links = Array.from(compiled.querySelectorAll<HTMLAnchorElement>('a.choice'));
    expect(links).toHaveLength(2);
    expect(links[0].getAttribute('href')).toBe('/ask-museum');
    expect(links[1].getAttribute('href')).toBe('/submit-proposal');
    expect(compiled.textContent).toContain('Ask the Museum');
    expect(compiled.textContent).toContain('Request an in-situ visit');
  });
});
