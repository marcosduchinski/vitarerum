import { highlightToSafeMarkup } from './highlight-html.util';

describe('highlightToSafeMarkup', () => {
  it('converts the backend <b> markers to <mark>', () => {
    expect(highlightToSafeMarkup('<b>Jaguar</b> found near the river')).toBe(
      '<mark>Jaguar</mark> found near the river',
    );
  });

  it('escapes unrelated markup instead of letting it through as HTML', () => {
    const result = highlightToSafeMarkup('<img src=x onerror=alert(1)> <b>Jaguar</b>');
    expect(result).not.toContain('<img');
    expect(result).toContain('&lt;img');
    expect(result).toContain('<mark>Jaguar</mark>');
  });

  it('escapes ampersands so the output cannot be re-interpreted as markup', () => {
    expect(highlightToSafeMarkup('Fish & Chips <b>shop</b>')).toBe(
      'Fish &amp; Chips <mark>shop</mark>',
    );
  });
});
