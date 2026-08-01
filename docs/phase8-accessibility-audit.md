# Phase 8 accessibility audit

Date: 2026-08-01
Target: WCAG 2.2 AA-oriented release hardening

## Automated and interaction result

Seventeen axe-core 4.12.1 scans run in real system Chrome cover six desktop
routes in both themes plus five representative 390px mobile routes. The final
result is zero serious or critical violations for the selected WCAG 2.0/2.1/
2.2 A/AA tags.

Keyboard journeys verify skip-link navigation, command-search open/close,
search result selection, table sorting, disclosures, screener editing, mobile
drawer focus containment, Escape behavior, and trigger focus restoration.
Status/copy feedback is exposed through live regions. Static content and primary
links remain useful without JavaScript.

Responsive checks cover 1440, 1024, 768, 390, 360 and 320 CSS pixels, effective
200% browser zoom, reduced-motion preference and minimum 24px button targets.
Tables that need two-dimensional scrolling are named and keyboard-focusable.

## Defects found and fixed

- The collapsed mobile search trigger had no computed accessible name: added an
  explicit `aria-label`.
- Light secondary text and the dark primary-button label missed contrast:
  corrected design tokens and button weight.
- Filter-chip ARIA was prohibited on its prior container: replaced it with a
  labelled group.
- Sector and company financial scroll regions were not keyboard focusable:
  added labelled focus targets; history and peer scrollers follow the same rule.
- Sort buttons were 16.5px tall on mobile: raised their minimum target height to
  24 CSS pixels.

## Assistive-technology limitation

A real macOS accessibility-tree/VoiceOver check was attempted through the
available computer-control interface. Application discovery succeeded, but the
Firefox accessibility-state read did not return and was terminated after a
bounded wait. VoiceOver speech/navigation was therefore not observed, and no
screen-reader pass is claimed.

Before production promotion, a human must run VoiceOver + Safari through the
rankings, search, screener builder/results, complete company, missing-financial
company and mobile navigation journeys. Confirm landmark order, table names,
chart alternative text, live feedback and disclosure state announcements.
