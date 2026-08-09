# Participant portal

The participant portal is the React/Vite application served at `/participant/`. It uses real FastAPI authentication, protected routes, SQLAlchemy-backed participant data, and the authenticated `/ws/auction` event stream.

```bash
npm ci
npm run typecheck
npm run build
```

Production defaults to same-origin `/api`; the WebSocket URL is derived from the browser origin. Copy `.env.example` only when a local API override is needed.
