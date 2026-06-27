import {
  afterNextRender,
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  input,
  output,
  viewChild,
} from '@angular/core';

const TURNSTILE_SCRIPT_SRC =
  'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit';

interface TurnstileApi {
  render(
    el: HTMLElement,
    options: {
      sitekey: string;
      callback: (token: string) => void;
      'error-callback'?: () => void;
      'expired-callback'?: () => void;
      theme?: 'auto' | 'light' | 'dark';
    },
  ): string;
  reset(widgetId?: string): void;
  remove(widgetId?: string): void;
}

declare global {
  interface Window {
    turnstile?: TurnstileApi;
  }
}

let scriptPromise: Promise<void> | null = null;

/** Loads the Turnstile script exactly once, on demand (browser only). */
function loadTurnstileScript(): Promise<void> {
  if (window.turnstile) return Promise.resolve();
  if (scriptPromise) return scriptPromise;

  scriptPromise = new Promise<void>((resolve, reject) => {
    const script = document.createElement('script');
    script.src = TURNSTILE_SCRIPT_SRC;
    script.async = true;
    script.defer = true;
    script.onload = () => resolve();
    script.onerror = () => {
      scriptPromise = null;
      reject(new Error('Failed to load Cloudflare Turnstile'));
    };
    document.head.appendChild(script);
  });
  return scriptPromise;
}

/**
 * Renders a Cloudflare Turnstile widget and emits its token. The script is
 * lazy-loaded so it only ships to the public page, never the authenticated app.
 *
 * The emitted token is a *client-side proof of interaction only* — it is
 * meaningless until the server verifies it via siteverify.
 */
@Component({
  selector: 'app-turnstile',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<div #host class="turnstile-host"></div>`,
  styles: `
    .turnstile-host {
      min-height: 65px;
    }
  `,
})
export class TurnstileComponent {
  /** Public Turnstile site key (from runtime config). */
  readonly siteKey = input.required<string>();

  /** Emits the verification token when the challenge is solved. */
  readonly verified = output<string>();
  /** Emits when the token expires or the challenge errors (token is invalid). */
  readonly invalidated = output<void>();

  private readonly host = viewChild.required<ElementRef<HTMLElement>>('host');
  private widgetId: string | null = null;

  constructor() {
    afterNextRender(() => {
      void this.renderWidget();
    });
  }

  /** Re-arms the widget after a failed submit so the citizen can retry. */
  reset(): void {
    if (this.widgetId && window.turnstile) {
      window.turnstile.reset(this.widgetId);
    }
  }

  private async renderWidget(): Promise<void> {
    try {
      await loadTurnstileScript();
    } catch {
      this.invalidated.emit();
      return;
    }
    if (!window.turnstile) {
      this.invalidated.emit();
      return;
    }

    this.widgetId = window.turnstile.render(this.host().nativeElement, {
      sitekey: this.siteKey(),
      theme: 'auto',
      callback: (token: string) => this.verified.emit(token),
      'error-callback': () => this.invalidated.emit(),
      'expired-callback': () => this.invalidated.emit(),
    });
  }
}
