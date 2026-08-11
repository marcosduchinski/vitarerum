import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import { PublicLocale } from './public-i18n.model';

/** Unique per instance: the Union Jack needs clip paths, and duplicate ids
 * across two flags on one page would make the second render wrong. */
let nextId = 0;

/**
 * Small decorative flag for the public language switcher.
 *
 * Drawn as inline SVG rather than a flag emoji because Windows does not render
 * regional-indicator emoji — it shows the two letters instead, which on a
 * public page reads as a bug. Purely decorative: the switcher already names
 * each language in text, so this is hidden from assistive tech.
 */
@Component({
  selector: 'app-locale-flag',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (locale() === 'pt-PT') {
      <svg viewBox="0 0 600 400" aria-hidden="true" focusable="false" class="locale-flag">
        <rect width="600" height="400" fill="#da291c" />
        <rect width="240" height="400" fill="#046a38" />
        <!-- Armillary sphere, simplified to the rings that read at this size. -->
        <g fill="none" stroke="#ffe000" stroke-width="14">
          <circle cx="240" cy="200" r="86" />
          <ellipse cx="240" cy="200" rx="38" ry="86" />
          <path d="M154 200h172M240 114v172" />
        </g>
        <path
          d="M240 130a70 70 0 0 1 48 19v72c0 34-23 56-48 66-25-10-48-32-48-66v-72a70 70 0 0 1 48-19z"
          fill="#fff"
          stroke="#da291c"
          stroke-width="14"
        />
      </svg>
    } @else {
      <svg viewBox="0 0 60 30" aria-hidden="true" focusable="false" class="locale-flag">
        <clipPath [attr.id]="frameId()">
          <path d="M0,0 v30 h60 v-30 z" />
        </clipPath>
        <clipPath [attr.id]="diagonalId()">
          <path d="M30,15 h30 v15 z v15 h-30 z h-30 v-15 z v-15 h30 z" />
        </clipPath>
        <g [attr.clip-path]="'url(#' + frameId() + ')'">
          <path d="M0,0 v30 h60 v-30 z" fill="#012169" />
          <path d="M0,0 L60,30 M60,0 L0,30" stroke="#fff" stroke-width="6" />
          <path
            d="M0,0 L60,30 M60,0 L0,30"
            [attr.clip-path]="'url(#' + diagonalId() + ')'"
            stroke="#c8102e"
            stroke-width="4"
          />
          <path d="M30,0 v30 M0,15 h60" stroke="#fff" stroke-width="10" />
          <path d="M30,0 v30 M0,15 h60" stroke="#c8102e" stroke-width="6" />
        </g>
      </svg>
    }
  `,
  styles: `
    :host {
      display: inline-flex;
    }
    .locale-flag {
      display: block;
      width: 1.35rem;
      height: auto;
      border-radius: 2px;
      // The white in both flags needs an edge against a light background.
      box-shadow: 0 0 0 1px rgb(0 0 0 / 0.18);
    }
  `,
})
export class LocaleFlagComponent {
  readonly locale = input.required<PublicLocale>();

  private readonly id = nextId++;
  protected readonly frameId = computed(() => `locale-flag-frame-${this.id}`);
  protected readonly diagonalId = computed(() => `locale-flag-diagonal-${this.id}`);
}
