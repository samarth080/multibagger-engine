# Phase 8 performance report

Date: 2026-08-01

## Result

The static architecture remains bounded and framework-free. Serial real-Chrome
instrumentation passed LCP <2.5s, CLS <=0.1, total blocking time <=200ms,
individual long task <=100ms and <=8-resource route budgets for rankings,
screener, canonical company and methodology pages on the local unthrottled lab.

Lighthouse 13.4.1 mobile-lab results against the local static server:

| Route | Perf | A11y | Best practices | SEO | FCP ms | LCP ms | CLS | TBT ms | Requests | Bytes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Rankings | 94 | 100 | 96 | 100 | 1,569 | 2,965 | 0 | 15 | 8 | 320,431 |
| Screener | 89 | 100 | 100 | 100 | 1,202 | 3,763 | 0.048 | 0 | 9 | 515,191 |
| Company | 100 | 100 | 96 | 100 | 1,202 | 1,652 | 0 | 0 | 7 | 122,632 |
| Methodology | 100 | 100 | 100 | 100 | 1,052 | 1,502 | 0 | 0 | 5 | 101,046 |

These are synthetic lab measurements, not field Core Web Vitals. The local
server does not implement the Vercel `/api/quotes` function, so the expected
404 lowers best-practices on quote-enhanced routes; API-unavailable behavior is
separately tested. Vercel compression and response headers are not represented.

## Static budgets

- CSS: 36,947 bytes (100KB release ceiling; 40KB browser-test ceiling).
- Application JavaScript: 51,580 bytes (100KB/60KB ceilings).
- Screener JavaScript: 38,253 bytes (100KB/50KB ceilings).
- Largest company HTML: 30,271 bytes (300KB/35KB ceilings).
- All 250 company/research payload count and maximum budgets pass.

Rankings and screener remain the heaviest routes because the static compatibility
mode downloads versioned universe data. Their server-rendered first view remains
useful before enhancement. Preview testing must confirm CDN compression and
repeat-view caching; a future optimization may split the static screener
payload only if measured field data justifies the added complexity.
