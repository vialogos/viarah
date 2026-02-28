# ViaRah

## OpenAI Dev Challenge

We're excited to submit Viarah! to the OpenAI developer challenge.

### How Codex was used?

The entire Viarah! application was first researched, then scoped and planned into milestones and issues, and finally autonomously built over a period of several days of non-stop coding sessions. Exclusively built by GPT 5.2 Xhigh inside of Codex CLI, via multi-agent orchestration workflows that carefully triage, resolve, review, test, and release. The longest uninterrupted single coding session lasted over 9 hours and 20 minutes. Issues are included in the public repo that capture the entire process for those interested.

Humans were in the loop after the first MVP build finished to iterate with Codex on predominantly front-end improvements and some enhancements to Viarah!'s initial set of features.

At the time of writing, Viarah! is undergoing internal testing and will receive some additional updates before being production-ready in the coming days or weeks. Viarah! is designed to be operated by Codex first, as our PMs and engineers will use natural language to perform operations like "create a new report with team availability over the holidays with a calendar and list view" or "I'm available for 3 extra hours on Saturday", or "Update the client that the dashboard preview is ready", etc. A handful of human interfaces will therefore benefit from—and see—a number of UX and quality of life improvements in the coming days.

We hope you enjoy Viarah! If you want to drop us a line, please find us at team@vialogos.org and https://via-logos.com.

Enjoy!

ViaRah is a **self-hostable delivery workspace** for teams shipping client work. It keeps planning, execution, client visibility, and deliverables in one place — and it’s built to be automation-friendly so agents can run real workflows end-to-end.

## Quick links (source of truth)

- **Official repo (source of truth):** https://gitlab.vialogos.dev/vialogos-labs/viarah
- **Releases:** https://gitlab.vialogos.dev/vialogos-labs/viarah/-/releases
- **Issues / roadmap:** https://gitlab.vialogos.dev/vialogos-labs/viarah/-/issues
- **Merge requests:** https://gitlab.vialogos.dev/vialogos-labs/viarah/-/merge_requests
- **Wiki (install + operator guide):** https://gitlab.vialogos.dev/vialogos-labs/viarah/-/wikis/home
- **Companion CLI (`viarah-cli`):** https://gitlab.vialogos.dev/vialogos-labs/viarah-cli
- **Via Logos (author):** https://via-logos.com
- **Contact:** https://via-logos.com/contact/

## GitHub mirror note (OpenAI dev challenge)

A public GitHub mirror exists only for the OpenAI dev challenge. All authoritative development, issue tracking, merge requests, and releases happen in the official GitLab at `gitlab.vialogos.dev`.

## Who it’s for

- **PMs / delivery leads** who need clear progress, repeatable reporting, and client-safe visibility
- **Engineering teams** who want a predictable workflow and strong automation hooks
- **Agencies / consultancies** delivering work in stages with SoWs, reports, and client sharing

## What ViaRah gives you

### Work tracking (the core)

- **Projects → Epics → Tasks → Subtasks** with assignments and scheduling fields
- **Time estimates** on work items to support planning and delivery forecasting
- **Workflow stages** (ordered stages) to keep progress tracking consistent across a project
- **Client visibility controls** so you can keep internal work internal while still sharing progress

### Views for planning and scheduling

- **Kanban board** (board view) for stage-based execution
- **Timeline roadmap** (timeline view) for higher-level schedule visibility
- **Gantt** (gantt view) for schedule-driven planning

### Client portal

- A dedicated **client portal** experience under `/client/*`
- Client users see only **client-safe** work and client-allowed detail surfaces
- Client-accessible schedule views (client timeline + client gantt) designed to avoid internal-only data

### Deliverables (reports + SoWs)

- **Liquid templates** (versioned) for consistent, repeatable output
- **Reports** rendered to HTML/PDF with run history + render logs
- **Public share links** for report runs (token shown once; server stores only a hash)
  - Share links support **expiry** and include **access logs**
- **Statements of Work (SoWs)** with versions, signers, and PDF artifacts

### Collaboration + communication

- **Comments** and **file attachments** on work items
- **Outbound drafts** (email/comment drafts rendered from templates)

### Notifications (including push)

- **In-app notifications** plus **email delivery logs**
- Optional **Web Push notifications** (when configured)

### Git integration (GitLab)

- Per-org **GitLab integration** configuration (base URL + token stored encrypted)
- **Live links** from tasks to GitLab issues/MRs with metadata refresh
- Optional **webhook ingestion** (with a webhook secret) to keep links up to date

### Automation & agents: `viarah-cli`

ViaRah is designed to be operated by humans *and* automation.

The companion **`viarah-cli`** uses ViaRah API keys and allows tools/agents (e.g., Codex) to perform ViaRah operations via **natural language** workflows — creating plans, generating reports/SoWs, updating work, and keeping delivery artifacts current.

## Quickstart (local development)

This is a minimal local quickstart. For production/self-hosting guidance and full setup details, use the Wiki:
https://gitlab.vialogos.dev/vialogos-labs/viarah/-/wikis/home

### Backend (Docker Compose)

```bash
cp .env.example .env
docker compose up -d --build
docker compose exec web python manage.py migrate
curl -fsS http://localhost:8000/healthz
```

Bootstrap the first org/PM/project (idempotent):

```bash
docker compose exec web python manage.py bootstrap_v1 \
  --org-name "Org" \
  --pm-email "pm@example.com" \
  --project-name "Project" \
  --api-key-name "viarah-cli" \
  --write-token-file /tmp/viarah_bootstrap_token.json
```

### Frontend (Vite + Vue)

```bash
cd frontend
npm install
npm run dev
```

- Frontend: http://localhost:5173/
- Backend: http://localhost:8000/

## Documentation inside the repo

For installation and operator guidance, use the Wiki:
https://gitlab.vialogos.dev/vialogos-labs/viarah/-/wikis/home

## Contributing

Please contribute via the official GitLab repo:
https://gitlab.vialogos.dev/vialogos-labs/viarah

- Open issues: https://gitlab.vialogos.dev/vialogos-labs/viarah/-/issues
- Submit merge requests: https://gitlab.vialogos.dev/vialogos-labs/viarah/-/merge_requests

(Changes proposed only on the GitHub mirror may be missed, since it’s not the primary tracker.)

## License

See `LICENSE`.
