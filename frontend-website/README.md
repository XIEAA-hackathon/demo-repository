# Bid to Build Frontend

One React/Vite application serves the public site, participant portal, Event Admin, Lab Admin and authenticated leaderboard display. The operational portals connect to the FastAPI backend over REST and WebSockets.

## Local Development

Set up PostgreSQL and the backend using the [root README](../README.md#running-locally), then run from this directory:

```bash
npm ci
npm run dev
```

The default browser origin is `http://localhost:5173`; development API calls default to `http://localhost:8000`. Optional `VITE_API_URL` and `VITE_WS_URL` overrides can be placed in a local `.env`. Production builds default to same-origin `/api`.

## Routes

| Route | Surface |
| --- | --- |
| `/`, `/event` | Public information |
| `/login` | Portal entry page |
| `/participant/*` | Participant login and event workflow |
| `/admin/*` | Event Admin login and control center |
| `/lab-admin/*` | Restricted Lab Admin login and allocation views |
| `/leaderboard` | Authenticated live event display |

## Source Guide

- `src/App.tsx`: shared router and lazy-loaded portals.
- `src/pages/public/`, `src/components/home/`: public pages and homepage sections.
- `src/config/eventContent.ts`: public event content.
- `src/admin/`, `src/participant/`, `src/lab-admin/`, `src/leaderboard/`: role-specific interfaces.
- `src/labs/`: shared lab allocation views.
- `src/services/api/` and `src/services/realtime/`: API configuration, authenticated requests and reconnect/timer utilities.
- `src/shared/components/StyleBoundary.tsx`: portal style isolation.
- `src/styles/theme.css`: public theme tokens.

## Build Validation

```bash
npm run typecheck
npm run build
```

`npm run preview` previews the built assets locally. The stack uses React 18, Vite 5, TypeScript and JavaScript, React Router, Lucide React, Tailwind CSS and scoped CSS.

See [LICENSE](LICENSE).

