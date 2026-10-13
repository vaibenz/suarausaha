import { describe, expect, it } from 'vitest';
import { contrastRatio, pairs, themes } from './theme.js';

// axe cannot measure colour contrast in jsdom (there is no layout or paint),
// so contrast is verified here directly from the design tokens.

describe('colour contrast', () => {
  it('computes the WCAG ratio correctly', () => {
    expect(contrastRatio('#000000', '#ffffff')).toBeCloseTo(21, 5);
    expect(contrastRatio('#777777', '#ffffff')).toBeCloseTo(4.48, 2);
  });

  for (const [themeName, theme] of Object.entries(themes)) {
    for (const [fg, bg, kind] of pairs) {
      const min = kind === 'ui' ? 3 : themeName === 'contrast' ? 7 : 4.5;
      it(`${themeName}: ${fg} on ${bg} is at least ${min}:1`, () => {
        expect(contrastRatio(theme[fg], theme[bg])).toBeGreaterThanOrEqual(min);
      });
    }
  }
});
