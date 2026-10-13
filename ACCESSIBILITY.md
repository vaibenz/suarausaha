# Accessibility

The target is WCAG 2.1 Level AA, with a high contrast mode that meets AAA contrast. The people this is for include warung owners with limited literacy, older owners with low vision, and anyone on a small, cheap phone in bright sunlight.

## What is checked automatically

| Check | How | Where |
|---|---|---|
| WCAG 2.0/2.1 A and AA rules plus best practices | axe-core run against the rendered app, on first load and again with entries, feedback and high contrast on | `frontend/src/App.test.jsx` |
| Text contrast 4.5:1 (AA), 7:1 in high contrast (AAA) | contrast ratio computed from every text and background token pair | `frontend/src/theme.test.js` |
| Non text contrast 3:1 for borders and focus rings | same | `frontend/src/theme.test.js` |
| Keyboard path: skip link first, focus returns to the input after saving | Testing Library with user-event | `frontend/src/App.test.jsx` |
| Status messages announced without moving focus | asserts `role="status"` and `aria-live="polite"` content | `frontend/src/App.test.jsx` |

axe cannot measure colour contrast in jsdom because there is no layout, which is why contrast is tested from the design tokens instead.

## Design decisions mapped to WCAG 2.1

| Criterion | Implementation |
|---|---|
| 1.1.1 Non text content | The mic icon is decorative (`aria-hidden`); the button always has visible text that changes with state. |
| 1.3.1 Info and relationships | Real headings, `label` for the input, a `table` with `caption` and `th scope="col"`, `dl` for the summary. |
| 1.4.1 Use of colour | Feedback starts with "Berhasil:" or "Perhatian:"; entry type is written as Jual or Beli; toggles show Aktif or Mati as text. |
| 1.4.3 / 1.4.6 Contrast | Tested tokens, AA by default and AAA in high contrast mode. |
| 1.4.4 Resize text | rem based sizes, an 18px base, and a Teks besar toggle that scales the whole interface. |
| 1.4.10 Reflow | Single column at 320px, the input and button stack on narrow screens, and the table scrolls inside a labelled, focusable region. |
| 1.4.11 Non text contrast | Borders and the focus ring are at least 3:1 against their backgrounds. |
| 2.1.1 Keyboard | Everything is a native button, link or input. The mic button uses `aria-disabled` rather than `disabled` when voice is unsupported, so keyboard users can still reach it and hear why. |
| 2.3.3 Animation | The recording pulse only runs under `prefers-reduced-motion: no-preference`. |
| 2.4.1 Bypass blocks | A skip link is the first focusable element. |
| 2.4.7 Focus visible | 3px focus ring with offset, in a colour tested against both backgrounds. |
| 2.5.5 Target size (AAA) | Every control is at least 48 by 48 CSS pixels; the mic button is 180px. |
| 3.1.1 Language of page | `lang="id"`; speech recognition and speech synthesis both use `id-ID`. |
| 3.3.1 / 3.3.3 Error identification and suggestion | Errors say what is missing ("Harga untuk kopi belum disebut.") and the empty state gives an example phrase. |
| 4.1.2 Name, role, value | Toggles and the mic button expose state with `aria-pressed`. |
| 4.1.3 Status messages | Confirmations and errors go to a polite live region and can also be read aloud. |

## Still to test by hand

Automated tools catch a share of issues, not all of them. Before calling this conformant, test with:

* TalkBack on a low end Android phone with Chrome, the most likely real device
* VoiceOver on iOS Safari
* NVDA with Firefox on Windows
* 200% browser zoom and 320px width
* Windows high contrast mode (forced colours)
