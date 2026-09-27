---
type: "query"
date: "2026-09-10T14:29:04.014206+00:00"
question: "Which former-main files are obsolete versus current main1 application code and current test tooling?"
contributor: "graphify"
outcome: "useful"
source_nodes: ["Backend Runtime Dependencies", "XIE Alumni Hackathon Public Frontend", "test_wildcard.py", "wildcard-load.js", "deploy-main1-remote.sh"]
---

# Q: Which former-main files are obsolete versus current main1 application code and current test tooling?

## Answer

The graph separated the consolidated frontend and backend runtime from test/load communities. That supported removing split frontend implementations, historical outputs, stale manual tests, old workflow and hard-coded load scripts while retaining current backend tests, consolidated-frontend tests, and sanitized k6 scenarios.

## Outcome

- Signal: useful

## Source Nodes

- Backend Runtime Dependencies
- XIE Alumni Hackathon Public Frontend
- test_wildcard.py
- wildcard-load.js
- deploy-main1-remote.sh