import { ChangeDetectionStrategy, Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter, Router, RouterOutlet, Routes } from '@angular/router';

import { PublicI18nService } from './i18n/public-i18n.service';
import { providePublicI18nTesting } from './i18n/public-i18n.testing';
import { PublicShellComponent } from './public-shell.component';

@Component({
  standalone: true,
  template: '',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
class StubPageComponent {}

/** Lets the router create the shell during route activation, as the real app
 * does — creating it directly would hide bugs that only surface while the
 * route tree is still being built. */
@Component({
  standalone: true,
  imports: [RouterOutlet],
  template: '<router-outlet />',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
class HostComponent {}

const CATALOG = {
  'public.appName': 'Vitarerum',
  'public.shell.home': 'Vitarerum — início',
  'public.shell.language': 'Idioma',
  'public.shell.language.pt-PT': 'Português',
  'public.shell.language.en': 'Inglês',
  'public.routes.askMuseum': 'Pergunte ao Museu',
};

/** Mirrors the three real public route trees: shell as the component route,
 * page as a child carrying the title key. */
function publicRoutes(childData: Record<string, string> = {}): Routes {
  return [
    {
      path: '',
      component: PublicShellComponent,
      children: [
        {
          path: '',
          pathMatch: 'full',
          data: childData,
          // Lazy, like every real public page: the child's snapshot is not
          // attached yet while the shell is being constructed.
          loadComponent: () => Promise.resolve(StubPageComponent),
        },
      ],
    },
  ];
}

async function shell(routes: Routes = publicRoutes({ titleKey: 'public.routes.askMuseum' })) {
  await TestBed.configureTestingModule({
    imports: [HostComponent],
    providers: [provideRouter(routes), providePublicI18nTesting('pt-PT', CATALOG)],
  }).compileComponents();

  const fixture = TestBed.createComponent(HostComponent);
  await TestBed.inject(Router).navigate(['/']);
  fixture.detectChanges();
  await fixture.whenStable();
  return fixture;
}

describe('PublicShellComponent', () => {
  it('links the public brand mark to the login screen', async () => {
    const root = (await shell()).nativeElement as HTMLElement;

    expect(root.querySelector<HTMLAnchorElement>('.public-shell__brand')?.getAttribute('href')).toBe(
      '/login',
    );
  });

  it('offers every supported language, with the active one selected', async () => {
    const root = (await shell()).nativeElement as HTMLElement;
    const options = Array.from(
      root.querySelectorAll<HTMLOptionElement>('.public-shell__language option'),
    );

    expect(options.map((option) => option.value)).toEqual(['pt-PT', 'en']);
    expect(options.map((option) => option.textContent?.trim())).toEqual(['Português', 'Inglês']);
    expect(options.find((option) => option.selected)?.value).toBe('pt-PT');
  });

  it('flies the flag of the active language, and swaps it on a switch', async () => {
    const fixture = await shell();
    const root = fixture.nativeElement as HTMLElement;
    // The two flags are told apart by their viewBox: the Portuguese drawing is
    // 600x400, the Union Jack 60x30.
    const flagViewBox = () =>
      root.querySelector('app-locale-flag svg')?.getAttribute('viewBox');

    expect(flagViewBox()).toBe('0 0 600 400');

    const select = root.querySelector<HTMLSelectElement>('.public-shell__language');
    select!.value = 'en';
    select!.dispatchEvent(new Event('change'));
    await fixture.whenStable();
    fixture.detectChanges();

    expect(flagViewBox()).toBe('0 0 60 30');
  });

  it('hides the flag from assistive tech, which already gets the language by name', async () => {
    const root = (await shell()).nativeElement as HTMLElement;

    expect(root.querySelector('app-locale-flag svg')?.getAttribute('aria-hidden')).toBe('true');
  });

  it('switches the active locale when a language is picked', async () => {
    const fixture = await shell();
    const select = (fixture.nativeElement as HTMLElement).querySelector<HTMLSelectElement>(
      '.public-shell__language',
    );

    select!.value = 'en';
    select!.dispatchEvent(new Event('change'));
    await fixture.whenStable();

    expect(TestBed.inject(PublicI18nService).locale()).toBe('en');
  });

  it('titles the document from the active route key, translated', async () => {
    await shell();

    expect(document.title).toBe('Pergunte ao Museu | Vitarerum');
  });

  it('shows the app name alone when the route carries no title key', async () => {
    await shell(publicRoutes());

    expect(document.title).toBe('Vitarerum');
  });
});
