# ViaRah (Frontend UI Conventions)


**HARD RULE — Tool output truncation:** `functions.exec_command` output can be truncated/capped (even when `max_output_tokens` is high). Never claim you read a file start-to-finish unless you verified full coverage via chunked reads (e.g., `nl -ba <file> | sed -n 'N,Mp'`).
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
  - `cd frontend && npm run dev`
  - `npm run dev` is pinned to `vite --host :: --port 5173 --strictPort` for Windows/WSL2 browser compatibility (covers IPv4 + IPv6 localhost).
- Open in your browser:
  - Windows: `http://localhost:5173/` (WSL localhost forwarding)
  - IPv4 fallback: `http://127.0.0.1:5173/`
  - Fallback: `http://<WSL_IP>:5173/` where `<WSL_IP>` is `wsl hostname -I` (first IP)
- If Windows cannot connect:
  - Verify from Windows shell:
    - `powershell.exe -NoProfile -Command "Test-NetConnection -ComputerName localhost -Port 5173 | Select-Object TcpTestSucceeded,RemoteAddress"`
    - `powershell.exe -NoProfile -Command "curl.exe -I http://localhost:5173/"`
  - Restart WSL networking: `wsl.exe --shutdown` (PowerShell), then retry `http://localhost:5173/`.
  - Last resort (PowerShell, portproxy):
    - `netsh interface portproxy add v4tov4 listenaddress=127.0.0.1 listenport=5173 connectaddress=<WSL_IP> connectport=5173`
    - Ensure Windows Firewall allows inbound to `127.0.0.1:5173` (portproxy traffic can be blocked).
