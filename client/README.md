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
