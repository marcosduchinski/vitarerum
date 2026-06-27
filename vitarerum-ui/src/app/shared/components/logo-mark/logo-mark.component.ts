import { ChangeDetectionStrategy, Component } from '@angular/core';

/**
 * The Vitarerum brand mark (vector redraw of public/vita03.png): an upward
 * ink triangle, a flame circle with a comma tail, the V letterform, and a
 * downward ink quadrilateral. Colours are themable so the mark stays legible
 * on ink surfaces:
 *   --logo-ink   ink shapes  (default brand navy  #022149)
 *   --logo-flame red shapes  (default brand vermilion #f43e1a)
 * Decorative by default; pair it with a visible text label.
 */
@Component({
  selector: 'app-logo-mark',
  standalone: true,
  templateUrl: './logo-mark.component.html',
  styleUrl: './logo-mark.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class LogoMarkComponent {}
