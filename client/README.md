# Inbox2Done web client

React + TypeScript + Vite. See the [root README](../README.md) for complete setup.

```sh
npm ci
npm run dev
npm test
npm run lint
npm run build
npx playwright install chromium
npm run test:e2e
```

Use `http://localhost:5173` during development. Vite proxies `/api` and `/health` to `127.0.0.1:8000`. Nginx does the same in the web container using `API_UPSTREAM` (default `api:8000`). There are no frontend secrets or API-key configuration fields.

The application requires a real authenticated backend session. Test mocks are confined to the test suites. Playwright writes desktop and mobile screenshots into ignored `test-results/`.

## Current experience

`App.tsx` checks the authenticated session and shows Google sign-in. `Today.tsx` loads today's Primary inbox using the browser time zone, then presents one daily briefing after the user clicks Analyze.

- Page load, Refresh today, and local-day rollover fetch Gmail without requesting new AI analysis.
- What matters today combines important summaries; Your action items combines tasks with saved completion state.
- Source subjects and suggested replies are expandable. Copying a reply does not send email or create a Gmail draft.
- API job polling updates partial progress. Saved unchanged analyses are reused.
- Legacy billing endpoints remain on the backend; this screen does not include billing controls.

Browser tests use synthetic mail and mocked API responses. They verify the explicit analysis action, task persistence across reload, copying replies, mobile overflow, and sign-out.
