import { PublicI18nCatalog } from '../public-i18n.model';

/** English translation of the source catalogue (`pt-PT.ts`). */
export const EN_CATALOG = {
  'public.appName': 'Vitarerum',

  'public.shell.home': 'Vitarerum — home',
  'public.shell.language': 'Language',
  'public.shell.language.pt-PT': 'Portuguese',
  'public.shell.language.en': 'English',

  'public.routes.landing': 'Vitarerum',
  'public.routes.askMuseum': 'Ask the Museum',
  'public.routes.askMuseumReceived': 'Question received',
  'public.routes.submitProposal': 'Submit a proposal',
  'public.routes.submissionReceived': 'Request received',
  'public.routes.submissionConfirm': 'Confirm your request',
  'public.routes.submissionEdit': 'Correct your documents',

  'public.landing.eyebrow': 'Welcome',
  'public.landing.title': 'How can we help?',
  'public.landing.description':
    'Choose the option that best fits what you need — a quick question, or a formal request to access our collections.',
  'public.landing.askMuseum.title': 'Ask the Museum',
  'public.landing.askMuseum.description':
    "Have a simple question about our collections, especially in-situ visits for research? Ask here and we'll reply by e-mail.",
  'public.landing.submitProposal.title': 'Request an in-situ visit',
  'public.landing.submitProposal.description':
    'Submit a formal proposal to access our collections, with dates, supporting documents, and confirmation.',

  'public.askMuseum.eyebrow': 'Ask the Museum',
  'public.askMuseum.title': 'Ask the Museum',
  'public.askMuseum.description':
    "Have a quick question? Tell us who you are and what you'd like to know — we'll reply by e-mail.",
  'public.askMuseum.scopeNotice':
    'At this time, Ask the Museum is only available for questions related to the use of collections, especially in-situ visits for research. Questions about exhibitions, loans, events, educational activities, or other museum services will be closed with an e-mail reply.',
  'public.askMuseum.form.name.label': 'Full name',
  'public.askMuseum.form.name.required': 'Your name is required.',
  'public.askMuseum.form.email.label': 'E-mail',
  'public.askMuseum.form.email.placeholder': 'you@example.com',
  'public.askMuseum.form.email.invalid': 'A valid e-mail address is required.',
  'public.askMuseum.form.email.hint': "We'll send our reply here.",
  'public.askMuseum.form.subject.label': 'Subject',
  'public.askMuseum.form.subject.placeholder': 'Brief subject line',
  'public.askMuseum.form.subject.required': 'Subject is required.',
  'public.askMuseum.form.message.label': 'Message',
  'public.askMuseum.form.message.placeholder': 'Ask your question…',
  'public.askMuseum.form.message.required': 'Your question is required.',
  'public.askMuseum.form.images.label': 'Images',
  'public.askMuseum.form.images.listLabel': 'Selected images',
  'public.askMuseum.form.images.remove': 'Remove {{name}}',
  'public.askMuseum.form.images.hint':
    'Optional: up to 10 PNG or JPEG images, 5 MB each, 25 MB total.',
  'public.askMuseum.form.images.selected.one': '{{count}} image selected · {{size}} total',
  'public.askMuseum.form.images.selected.other': '{{count}} images selected · {{size}} total',
  'public.askMuseum.form.images.tooMany': 'Attach at most {{count}} images.',
  'public.askMuseum.form.images.invalidType': 'Only PNG and JPEG images are accepted.',
  'public.askMuseum.form.images.tooLarge': 'Each image must be 5 MB or smaller.',
  'public.askMuseum.form.images.totalTooLarge':
    'Image attachments must be 25 MB or smaller in total.',
  'public.askMuseum.form.consent.label':
    'I agree that Vitarerum may process the personal data in this form to handle my question.',
  'public.askMuseum.form.consent.required': 'Consent is required to submit.',
  'public.askMuseum.form.captcha.required': 'Please complete the verification.',
  'public.askMuseum.form.submit': 'Send question',
  'public.askMuseum.form.submitting': 'Sending…',

  'public.askMuseum.received.title': 'Question received',
  'public.askMuseum.received.message':
    "Thank you for your question. We've received it and will reply as soon as possible.",
  'public.askMuseum.received.messageTo':
    "Thank you for your question. We've received it and will reply to {{email}} as soon as possible.",
  'public.askMuseum.received.note':
    "We'll reply by e-mail. Didn't mean to send this? No action is needed —",
  'public.askMuseum.received.noteLink': 'ask another question',

  'public.submitProposal.eyebrow': 'Public submission',
  'public.submitProposal.title': 'Submit a proposal',
  'public.submitProposal.description':
    "Any member of the public may request access to our collections. Tell us who you are and what you need — we'll e-mail you a link to confirm your request.",
  'public.submitProposal.sections.details': 'Your details',
  'public.submitProposal.sections.request': 'Your request',
  'public.submitProposal.sections.requestHint':
    "Your proposal opens a conversation with the collections team. Describe what you'd like to access and why.",
  'public.submitProposal.form.name.label': 'Full name',
  'public.submitProposal.form.name.required': 'Your name is required.',
  'public.submitProposal.form.email.label': 'E-mail',
  'public.submitProposal.form.email.placeholder': 'you@example.com',
  'public.submitProposal.form.email.invalid': 'A valid e-mail address is required.',
  'public.submitProposal.form.email.hint':
    "We'll send a confirmation link here. Your request is only forwarded after you confirm.",
  'public.submitProposal.form.useType.label': 'Intended use',
  'public.submitProposal.form.useType.placeholder': "Select how you'll use the collection…",
  'public.submitProposal.form.useType.required': "Please choose how you'll use the collection.",
  'public.submitProposal.form.useType.unsupported':
    'Only in-situ visit requests are operational at the moment. Exhibition and other uses will be implemented later.',
  'public.submitProposal.useTypes.IN_SITU_VISIT': 'In-situ visit',
  'public.submitProposal.useTypes.EXHIBITION': 'Exhibition',
  'public.submitProposal.useTypes.OTHER': 'Other',
  'public.submitProposal.templates.title': 'Required documents',
  'public.submitProposal.templates.intro':
    'Download the template(s) below, fill them in and attach the completed files to your request.',
  'public.submitProposal.templates.mandatory': 'Mandatory',
  'public.submitProposal.form.dates.label': 'Proposed dates',
  'public.submitProposal.form.dates.from': 'From',
  'public.submitProposal.form.dates.to': 'To',
  'public.submitProposal.form.dates.required': 'Please give both a start and an end date.',
  'public.submitProposal.form.dates.invalidRange': "The end date can't be before the start date.",
  'public.submitProposal.form.dates.hint': 'When would you like to access the collection?',
  'public.submitProposal.form.subject.label': 'Subject',
  'public.submitProposal.form.subject.placeholder': 'Brief subject line',
  'public.submitProposal.form.subject.required': 'Subject is required.',
  'public.submitProposal.form.body.label': 'Message',
  'public.submitProposal.form.body.placeholder': 'Introduce yourself and describe what you need…',
  'public.submitProposal.form.body.required': 'Message body is required.',
  'public.submitProposal.form.documents.label': 'Supporting documents',
  'public.submitProposal.form.documents.listLabel': 'Selected supporting documents',
  'public.submitProposal.form.documents.remove': 'Remove',
  'public.submitProposal.form.documents.hint':
    'Attach 1-5 files. PDF, JPG, PNG, and DOCX are accepted, up to 10 MB each.',
  'public.submitProposal.form.documents.required': 'Attach at least one supporting document.',
  'public.submitProposal.form.documents.tooMany':
    'Attach no more than five supporting documents.',
  'public.submitProposal.form.documents.tooLarge': '{{name}} is larger than 10 MB.',
  'public.submitProposal.form.documents.invalidType': '{{name}} is not a supported file type.',
  'public.submitProposal.form.consent.label':
    'I agree that Vitarerum may process the personal data in this form to handle my request.',
  'public.submitProposal.form.consent.required': 'Consent is required to submit.',
  'public.submitProposal.form.captcha.required': 'Please complete the verification.',
  'public.submitProposal.form.submit': 'Submit proposal',
  'public.submitProposal.form.submitting': 'Submitting…',

  'public.submitProposal.received.title': 'Almost there — check your inbox',
  'public.submitProposal.received.message':
    "We've sent a confirmation link. Click it to forward your request to the collections team. The link expires in 24 hours.",
  'public.submitProposal.received.messageTo':
    "We've sent a confirmation link to {{email}}. Click it to forward your request to the collections team. The link expires in 24 hours.",
  'public.submitProposal.received.note':
    "Didn't get the e-mail? It can take a few minutes. Check your spam folder, or",
  'public.submitProposal.received.noteLink': 'start a new request',

  'public.submitProposal.confirm.loading': 'Confirming your request…',
  'public.submitProposal.confirm.startNew': 'Start a new request',
  'public.submitProposal.confirm.CONFIRMED.title': 'Request confirmed',
  'public.submitProposal.confirm.CONFIRMED.message':
    'Thank you — your proposal has been forwarded to the collections team. They will reply to your e-mail.',
  'public.submitProposal.confirm.ALREADY_CONFIRMED.title': 'Already confirmed',
  'public.submitProposal.confirm.ALREADY_CONFIRMED.message':
    'This request was already confirmed. The collections team has it — no further action needed.',
  'public.submitProposal.confirm.EXPIRED.title': 'Link expired',
  'public.submitProposal.confirm.EXPIRED.message':
    'This confirmation link has expired. Please submit your request again to receive a fresh link.',
  'public.submitProposal.confirm.INVALID.title': 'Invalid link',
  'public.submitProposal.confirm.INVALID.message':
    'We couldn’t confirm this request. The link may be incomplete. Please submit your request again.',

  'public.submitProposal.edit.loading': 'Loading your correction request…',
  'public.submitProposal.edit.startNew': 'Start a new request',
  'public.submitProposal.edit.submitted.title': 'Documents submitted',
  'public.submitProposal.edit.submitted.message':
    'Thank you. The collections team has received your corrected documents.',
  'public.submitProposal.edit.conflict.title': 'This request is no longer editable',
  'public.submitProposal.edit.conflict.message':
    'The proposal has already moved forward. Please contact the collections team if you have questions.',
  'public.submitProposal.edit.invalid.title': 'Invalid or expired link',
  'public.submitProposal.edit.invalid.message':
    'This correction link is invalid, expired or already used.',
  'public.submitProposal.edit.eyebrow': 'Document correction',
  'public.submitProposal.edit.title': 'Correct your documents',
  'public.submitProposal.edit.description':
    'Proposal {{reference}} is waiting for the document changes requested below.',
  'public.submitProposal.edit.summaryLabel': 'Correction request summary',
  'public.submitProposal.edit.status': 'Status: {{status}}',
  'public.submitProposal.edit.expires': 'Link expires: {{date}}',
  'public.submitProposal.edit.replaceDocument': 'Replace document',
  'public.submitProposal.edit.attachMissingDocument': 'Attach missing document',
  'public.submitProposal.edit.uploaded': 'Uploaded',
  'public.submitProposal.edit.remove': 'Remove',
  'public.submitProposal.edit.removing': 'Removing…',
  'public.submitProposal.edit.replacementFile': 'Replacement file',
  'public.submitProposal.edit.documentFile': 'Document file',
  'public.submitProposal.edit.fileHint': 'Accepted formats: PDF, JPG, PNG or DOCX, up to 10 MB.',
  'public.submitProposal.edit.upload': 'Upload file',
  'public.submitProposal.edit.uploading': 'Uploading…',
  'public.submitProposal.edit.noPending.title': 'No pending document corrections',
  'public.submitProposal.edit.noPending.message':
    'There are no open document corrections for this link.',
  'public.submitProposal.edit.submit': 'Submit corrected documents',
  'public.submitProposal.edit.submitting': 'Submitting…',
  'public.submitProposal.edit.file.tooLarge': '{{name}} is larger than 10 MB.',
  'public.submitProposal.edit.file.invalidType': '{{name}} is not a supported file type.',

  'public.submitProposal.statuses.REQUESTED': 'Requested',
  'public.submitProposal.statuses.RESOLVED': 'Resolved',
  'public.submitProposal.statuses.PENDING_DOCUMENTS': 'Pending documents',
  'public.submitProposal.statuses.SUBMITTED': 'Submitted',
} as const satisfies PublicI18nCatalog;
