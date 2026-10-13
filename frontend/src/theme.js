// Colour tokens for both themes. They are applied as CSS custom properties, and
// src/theme.test.js checks every text and control pair against WCAG 2.1 contrast:
// 4.5:1 for text in the default theme (AA), 7:1 in high contrast (AAA), and
// 3:1 for borders and focus rings (non text contrast, 1.4.11).

export const themes = {
  default: {
    bg: '#ffffff',
    surface: '#f3f5f7',
    text: '#14171a',
    muted: '#4a5561',
    primary: '#0b57a4',
    onPrimary: '#ffffff',
    success: '#1b6630',
    successBg: '#e7f4ea',
    danger: '#a3191c',
    dangerBg: '#fdecec',
    border: '#6b7683',
    focus: '#b34700',
  },
  contrast: {
    bg: '#000000',
    surface: '#000000',
    text: '#ffffff',
    muted: '#ffff66',
    primary: '#ffe500',
    onPrimary: '#000000',
    success: '#8cff8c',
    successBg: '#000000',
    danger: '#ff9c9c',
    dangerBg: '#000000',
    border: '#ffffff',
    focus: '#00e5ff',
  },
};

// [foreground, background, kind] pairs that appear in the UI
export const pairs = [
  ['text', 'bg', 'text'],
  ['text', 'surface', 'text'],
  ['muted', 'bg', 'text'],
  ['muted', 'surface', 'text'],
  ['primary', 'bg', 'text'],
  ['onPrimary', 'primary', 'text'],
  ['success', 'successBg', 'text'],
  ['danger', 'dangerBg', 'text'],
  ['border', 'bg', 'ui'],
  ['focus', 'bg', 'ui'],
  ['focus', 'surface', 'ui'],
];

function channel(c) {
  const v = c / 255;
  return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
}

export function luminance(hex) {
  const n = parseInt(hex.slice(1), 16);
  return 0.2126 * channel((n >> 16) & 255) + 0.7152 * channel((n >> 8) & 255) + 0.0722 * channel(n & 255);
}

export function contrastRatio(a, b) {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

export function cssVars(theme) {
  return Object.fromEntries(Object.entries(themes[theme]).map(([k, v]) => [`--${k}`, v]));
}
