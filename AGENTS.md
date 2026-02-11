# ViaRah (Frontend UI Conventions)

## PatternFly-first UI

- Prefer PatternFly Vue components (`@vue-patternfly/core` + `@vue-patternfly/table`) over custom HTML/CSS primitives.
- Consult `docs/patternfly-vue-component-inventory.md` before introducing a new UI primitive; keep it accurate as the UI evolves.

## Labels (Hard Rule)

- Use PatternFly **Label** via `frontend/src/components/VlLabel.vue` for all semantic tags (status/progress/sync/state/timestamps/changed, etc).
- Do not use custom “chips” or “badges” for semantic labels.

## Tables

- Any tabular data must use `<pf-table>` (avoid CSS grid “table” implementations).

