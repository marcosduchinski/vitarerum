// Backend search highlights (e.g. Postgres ts_headline() over spreadsheet cell
// content, uploader-controlled) wrap the matched term in <b>...</b> but do NOT
// escape the surrounding text. Escape everything first, then re-open only the
// exact <b>/</b> markers as <mark> — never trust the raw string as HTML.
function escapeHtml(text: string): string {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

export function highlightToSafeMarkup(highlight: string): string {
  return escapeHtml(highlight)
    .replace(/&lt;b&gt;/g, '<mark>')
    .replace(/&lt;\/b&gt;/g, '</mark>');
}
