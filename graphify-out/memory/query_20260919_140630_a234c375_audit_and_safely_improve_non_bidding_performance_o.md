---
type: "query"
date: "2026-09-19T14:06:30.968161+00:00"
question: "Audit and safely improve non-bidding performance on main1: images, route loading, redundant requests, async blocking, N+1 queries, startup, dependencies, and instrumentation."
contributor: "graphify"
outcome: "useful"
source_nodes: ["frontend-website/src/App.tsx", "frontend-website/src/participant/services/apiParticipantService.ts", "Backend/app/api/admin.py", "frontend-website/src/participant/ParticipantContext.tsx"]
---

# Q: Audit and safely improve non-bidding performance on main1: images, route loading, redundant requests, async blocking, N+1 queries, startup, dependencies, and instrumentation.

## Answer

Compressed six raster PNG assets to dimension-matched WebP (91.6% smaller); lazy-loaded participant, admin, lab-admin, and leaderboard route bundles; removed duplicate participant dashboard refreshes after three non-bid mutations; replaced admin export/account N+1 queries with fixed preloads and dictionary lookups; offloaded registration parsing and workbook generation from async endpoints; added export duration logging and focused query/request tests. Kept live data uncached, avoided unnecessary pagination/debounce/preload, preserved startup safety checks, and did not change bidding mechanics.

## Outcome

- Signal: useful

## Source Nodes

- frontend-website/src/App.tsx
- frontend-website/src/participant/services/apiParticipantService.ts
- Backend/app/api/admin.py
- frontend-website/src/participant/ParticipantContext.tsx