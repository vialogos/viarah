# ViaRah (Frontend UI Conventions)

## PatternFly-first UI

- Prefer PatternFly Vue components (`@vue-patternfly/core` + `@vue-patternfly/table`) over custom HTML/CSS primitives.
- Consult `docs/patternfly-vue-component-inventory.md` before introducing a new UI primitive; keep it accurate as the UI evolves.

## Labels (Hard Rule)

- Use PatternFly **Label** via `frontend/src/components/VlLabel.vue` for all semantic tags (status/progress/sync/state/timestamps/changed, etc).
- Do not use custom “chips” or “badges” for semantic labels.

## Tables

- Any tabular data must use `<pf-table>` (avoid CSS grid “table” implementations).

## Modals

- Prefer PatternFly modal components/patterns; do not use `window.confirm()` for user flows.

## Local Dev (WSL2 + Windows Browsers)

- Start the Vite dev server with an explicit host/port:
  - `cd frontend && npm run dev -- --host 0.0.0.0 --port 5173 --strictPort`
- Open in your browser:
  - Windows: `http://localhost:5173/` (WSL localhost forwarding)
  - Fallback: `http://<WSL_IP>:5173/` where `<WSL_IP>` is `wsl hostname -I` (first IP)
- If Windows cannot connect:
  - Restart WSL networking: `wsl.exe --shutdown` (PowerShell), then retry `http://localhost:5173/`.
  - Last resort (PowerShell, portproxy):
    - `netsh interface portproxy add v4tov4 listenaddress=127.0.0.1 listenport=5173 connectaddress=<WSL_IP> connectport=5173`
    - Ensure Windows Firewall allows inbound to `127.0.0.1:5173` (portproxy traffic can be blocked).
