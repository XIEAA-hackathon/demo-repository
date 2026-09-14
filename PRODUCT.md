# Bid to Build Product Context

Bid to Build is a single-event hackathon operations application for Event Admins, participant teams, leaderboard display operators, and a dedicated Lab Admin.

The Event Admin configures and runs Round 1, Wildcard, submissions, judging, participant credentials, and lab setup. Participant teams bid and receive a final effective problem statement. The Lab Admin uses a separate, role-restricted surface to place teams into configured physical labs after final problem assignments are known.

Lab allocation must preserve each team's Round 1 and Wildcard history, use the current effective problem, assign every approved non-system team exactly once, respect hard lab capacities, and keep one team per effective problem per lab during automatic allocation. Manual moves may override the problem-uniqueness rule only after an explicit warning; capacity can never be overridden.

The interface uses the existing dark Bid to Build visual system: compact operational layouts, restrained purple accents, precise spacing, small controls, and clear status/error language. Event and Lab Admin data stays synchronized through the existing bounded WebSocket transport without forcing participant dashboard reloads.
