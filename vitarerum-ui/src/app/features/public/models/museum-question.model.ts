/**
 * Payload a citizen submits from the public "Pergunte ao Museu" page.
 *
 * Security note: every field here is an *untrusted* input. The frontend only
 * does friendly validation (presence, email shape, consent) — the real
 * defences (Turnstile verification, rate-limiting, sanitisation) live on the
 * server. See docs/plans/museum-questions-public-page-plan.md.
 */
export interface MuseumQuestionSubmission {
  readonly requesterName: string;
  readonly requesterEmail: string;
  readonly subject: string;
  readonly message: string;
  /** RGPD consent — the citizen agreed to their data being processed. */
  readonly consent: boolean;
  /** Cloudflare Turnstile token; the server must verify it via siteverify. */
  readonly captchaToken: string;
  /**
   * Honeypot. Must stay empty for real humans (the field is visually hidden).
   * A non-empty value signals a bot; the server accepts-and-drops silently.
   */
  readonly website?: string;
}

/** Response to a successful submission (or a silent honeypot accept-and-drop). */
export interface MuseumQuestionReceipt {
  readonly status: 'RECEIVED';
  readonly email: string;
}
