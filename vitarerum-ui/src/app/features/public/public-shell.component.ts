import { DOCUMENT } from '@angular/common';
import { ChangeDetectionStrategy, Component, effect, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import {
  ActivatedRouteSnapshot,
  NavigationEnd,
  Router,
  RouterLink,
  RouterOutlet,
} from '@angular/router';
import { filter, map, startWith } from 'rxjs';

import { AppFooterComponent } from '@layout/footer/app-footer.component';
import { LogoMarkComponent } from '@shared/components/logo-mark/logo-mark.component';

import { LocaleFlagComponent } from './i18n/locale-flag.component';
import { PUBLIC_LOCALES, PublicLocale } from './i18n/public-i18n.model';
import { PublicI18nPipe } from './i18n/public-i18n.pipe';
import { PublicI18nService } from './i18n/public-i18n.service';

/**
 * Minimal chrome for the public (unauthenticated) pages: brand mark, language
 * switcher and footer — no sidebar, topbar, or role selector. Hosts the public
 * routes via outlet.
 *
 * The switcher lives here because the public pages have no topbar; without it a
 * citizen has no way to change language. The shell also owns the document
 * title, resolved from each route's `data.titleKey`, which avoids overriding the
 * app-wide `TitleStrategy` for the sake of seven public routes.
 */
@Component({
  selector: 'app-public-shell',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    RouterOutlet,
    RouterLink,
    AppFooterComponent,
    LogoMarkComponent,
    PublicI18nPipe,
    LocaleFlagComponent,
  ],
  templateUrl: './public-shell.component.html',
  styleUrl: './public-shell.component.scss',
})
export class PublicShellComponent {
  private readonly document = inject(DOCUMENT);
  private readonly router = inject(Router);

  protected readonly i18n = inject(PublicI18nService);
  protected readonly locales = PUBLIC_LOCALES;

  constructor() {
    const titleKey = toSignal(
      this.router.events.pipe(
        filter((event) => event instanceof NavigationEnd),
        startWith(null),
        map(() => this.deepestTitleKey()),
      ),
      { initialValue: this.deepestTitleKey() },
    );

    effect(() => {
      const key = titleKey();
      const appName = this.i18n.t('public.appName');
      const title = key ? this.i18n.t(key) : appName;
      this.document.title = title === appName ? appName : `${title} | ${appName}`;
    });
  }

  protected onLocaleChange(event: Event): void {
    void this.i18n.setLocale((event.target as HTMLSelectElement).value as PublicLocale);
  }

  /**
   * Walks the router's snapshot tree rather than the live `ActivatedRoute`
   * chain: while this component is being constructed the route tree is still
   * being activated, and a lazily loaded child has no `snapshot` attached yet.
   */
  private deepestTitleKey(): string | null {
    let current: ActivatedRouteSnapshot | null = this.router.routerState.snapshot.root;
    let key: string | null = null;
    while (current) {
      const candidate: unknown = current.data['titleKey'];
      if (typeof candidate === 'string') key = candidate;
      current = current.firstChild;
    }
    return key;
  }
}
