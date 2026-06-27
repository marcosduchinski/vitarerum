/**
 * Payload a citizen submits from the public (unauthenticated) proposal page.
 *
 * Security note: every field here is an *untrusted* input. The frontend only
 * does friendly validation (presence, email shape, consent) — the real
 * defences (Turnstile verification, rate-limiting, sanitisation, double
 * opt-in) live on the server. See provide-public-submission / the plan.
 */
export interface PublicProposalSubmission {
  readonly citizenName: string;
  readonly citizenEmail: string;
  readonly subject: string;
  readonly body: string;
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

/**
 * Response to a successful submission. No proposal exists yet — it is only
 * materialised after the citizen confirms via the e-mailed link (double
 * opt-in). We echo back the masked email so the "check your inbox" screen can
 * show where the confirmation was sent.
 */
export interface PublicSubmissionReceipt {
  readonly status: 'PENDING_CONFIRMATION';
  readonly email: string;
}

export type PublicConfirmationStatus = 'CONFIRMED' | 'ALREADY_CONFIRMED' | 'EXPIRED' | 'INVALID';

/** Result of clicking the confirmation link (POST /public/proposals/confirm). */
export interface PublicConfirmationResult {
  readonly status: PublicConfirmationStatus;
  /** Present once a proposal has been created, for staff-side reference. */
  readonly referenceNumber?: string;
}
