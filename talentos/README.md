# TalentOS

Agentic Talent Demand OS: employer reputation intelligence → competitive diagnosis → evidence-backed recommendations → human-approved talent campaigns → measurable hiring outcomes.

## Run
`npm install && npm run dev`

Open `http://localhost:3000`.

## Product surfaces
Command Center, Talent Intelligence, Competitive Intelligence, AI Reputation, Talent Segments, Campaigns, Employee Voices, Candidate Funnel, Analytics, Integrations and Governance.

## API
- `GET /api/health`
- `GET /api/intelligence`
- `GET /api/reputation`
- `GET /api/campaigns`
- `POST /api/campaigns`
- `POST /api/agent`

The demo uses deterministic seeded intelligence so the UX is immediately demoable. Replace `lib/data.ts` behind the stable API boundary with tenant-scoped repositories and live connector adapters for production.
