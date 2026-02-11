# PatternFly Vue Component Inventory and Coverage Matrix (Issue #45)

## Scope and method
- Upstream source read in full: `https://github.com/mtorromeo/vue-patternfly/tree/main/apps/docs/src/stories/Components`
- Total upstream component story entries read: `64`
- Baseline checks were run on this branch after rollback-equivalent commit `fb7d3a5`.
- Post-remediation checks were run after table + modal confirmation migration.

## Version-selection rationale (internet-verified)
Command outputs:
```text
$ npm view @vue-patternfly/core dist-tags
{ latest: '5.1.1' }

$ npm view @vue-patternfly/table dist-tags
{ latest: '6.0.0-alpha.1' }

$ npm view @vue-patternfly/table@6.0.0-alpha.1 peerDependencies
{ '@vueuse/core': '^13', '@vue-patternfly/core': '^6.0.0-beta.1' }

$ npm view @vue-patternfly/table@5.0.0 peerDependencies
{ '@vueuse/core': '^13', '@vue-patternfly/core': '^5.0.0' }
```
Decision:
- Keep `@vue-patternfly/core` on `5.1.1` and use `@vue-patternfly/table@5.0.0`.
- Rationale: `@vue-patternfly/table@latest` is pre-release (`6.0.0-alpha.1`) and requires core beta (`^6.0.0-beta.1`). This repo is on stable core v5 and needed the latest compatible stable table line.

References:
- https://github.com/mtorromeo/vue-patternfly/blob/main/apps/docs/src/stories/Overview/Introduction.story.vue
- https://github.com/mtorromeo/vue-patternfly/blob/main/apps/docs/src/stories/Components/Table.story.vue
- https://www.npmjs.com/package/@vue-patternfly/core?activeTab=versions
- https://www.npmjs.com/package/@vue-patternfly/table?activeTab=versions

## Baseline hard-gate findings and post-remediation result
Baseline (pre-remediation) evidence:
- Raw tables:
  - `frontend/src/pages/NotificationDeliveryLogsPage.vue:120`
  - `frontend/src/pages/NotificationSettingsPage.vue:485`
  - `frontend/src/pages/NotificationSettingsPage.vue:569`
  - `frontend/src/pages/TemplatesPage.vue:138`
  - `frontend/src/pages/OutputRunDetailPage.vue:424`
  - `frontend/src/pages/OutputRunDetailPage.vue:465`
  - `frontend/src/pages/OutputRunDetailPage.vue:507`
  - `frontend/src/pages/WorkflowEditPage.vue:287`
  - `frontend/src/pages/OutputsPage.vue:198`
  - `frontend/src/pages/WorkflowCreatePage.vue:169`
  - `frontend/src/pages/TemplateDetailPage.vue:143`
- Native confirms:
  - `frontend/src/pages/WorkListPage.vue:444`
  - `frontend/src/pages/WorkListPage.vue:521`
  - `frontend/src/pages/WorkflowEditPage.vue:209`
  - `frontend/src/pages/WorkflowEditPage.vue:235`

Post-remediation verification:
```text
rg -n "<table|window\.confirm|\bconfirm\(" frontend/src -g '*.vue' -g '*.ts' -g '*.js'
# no matches
```

## Full 64-story coverage matrix (post-remediation)
Legend:
- `Used`: component family is actively used in ViaRah UI.
- `Gap`: equivalent UI exists but is still implemented with non-PatternFly primitives.
- `Not applicable`: no current interface requirement in this codebase for this family.

| # | Story file | Post status | Evidence (file:line) | Gap remediation status |
|---|---|---|---|---|
| 1 | Accordion.story.vue | Not applicable | N/A | No accordion use case currently implemented. |
| 2 | ActionList.story.vue | Not applicable | N/A | No action-list layout pattern currently needed. |
| 3 | Alert.story.vue | Gap | `frontend/src/pages/WorkListPage.vue:658` | Replace custom `div.error` surfaces with `pf-alert`. |
| 4 | Avatar.story.vue | Not applicable | N/A | No avatar UI currently implemented. |
| 5 | BackgroundImage.iframe.vue | Not applicable | N/A | Story infrastructure file; no direct app use case. |
| 6 | BackgroundImage.story.vue | Not applicable | N/A | No background-image hero pattern in scope UI. |
| 7 | Badge.story.vue | Gap | `frontend/src/layouts/AppShell.vue:208` | Replace custom count badge spans with `pf-badge`. |
| 8 | Banner.story.vue | Not applicable | N/A | No banner-style announcement strip in current routes. |
| 9 | Brand.story.vue | Gap | `frontend/src/layouts/AppShell.vue:162` | Replace custom brand text blocks with `pf-brand` where branding asset is available. |
| 10 | Breadcrumb.story.vue | Not applicable | N/A | No breadcrumb navigation currently displayed. |
| 11 | Button.story.vue | Used | `frontend/src/components/VlConfirmModal.vue:38` | In use via PatternFly modal actions. |
| 12 | Card.story.vue | Gap | `frontend/src/pages/WorkListPage.vue:590` | Replace recurring `<div class="card">` containers with `pf-card` primitives. |
| 13 | Checkbox.story.vue | Gap | `frontend/src/pages/WorkListPage.vue:625` | Replace native checkboxes with `pf-checkbox` where available. |
| 14 | Chip.story.vue | Gap | `frontend/src/pages/WorkListPage.vue:679` | Replace ad-hoc chip spans with PF label/badge semantics per issue rule. |
| 15 | CloseButton.story.vue | Gap | `frontend/src/layouts/AppShell.vue:163` | Replace custom close icon button with `pf-close-button` in dismiss controls. |
| 16 | Content.story.vue | Gap | `frontend/src/pages/WorkListPage.vue:584` | Migrate rich text sections to `pf-text-content` primitives. |
| 17 | DataList.story.vue | Gap | `frontend/src/pages/WorkListPage.vue:667` | Task rows currently use custom lists; migrate to `pf-data-list` where suitable. |
| 18 | DescriptionList.story.vue | Gap | `frontend/src/pages/OutputRunDetailPage.vue:365` | Replace key/value metadata stacks with `pf-description-list`. |
| 19 | Divider.story.vue | Not applicable | N/A | No explicit divider component requirement yet. |
| 20 | Drawer.story.vue | Not applicable | N/A | No side-drawer interaction currently implemented. |
| 21 | Dropdown.story.vue | Not applicable | N/A | No PF dropdown menu pattern currently in use. |
| 22 | EmptyState.story.vue | Gap | `frontend/src/pages/NotificationDeliveryLogsPage.vue:124` | Replace plain empty text states with `pf-empty-state`. |
| 23 | ExpandableSection.story.vue | Not applicable | N/A | No expandable section pattern currently needed. |
| 24 | FileUpload.story.vue | Not applicable | N/A | No file upload flow in current frontend pages. |
| 25 | Form.story.vue | Gap | `frontend/src/pages/LoginPage.vue:37` | Migrate native form scaffolds to `pf-form` and `pf-form-group`. |
| 26 | FormSelect.story.vue | Gap | `frontend/src/pages/WorkListPage.vue:595` | Replace native selects with `pf-form-select`/`pf-select` patterns where suitable. |
| 27 | HelperText.story.vue | Gap | `frontend/src/pages/NotificationSettingsPage.vue:481` | Convert helper note text to `pf-helper-text`. |
| 28 | Hint.story.vue | Not applicable | N/A | No dedicated hint block pattern currently used. |
| 29 | Icon.story.vue | Gap | `frontend/src/layouts/AppShell.vue:163` | Icon usage is custom/lucide; evaluate PF icon primitives for consistency. |
| 30 | InputGroup.story.vue | Gap | `frontend/src/pages/OutputRunDetailPage.vue:377` | Replace custom token input row with `pf-input-group`. |
| 31 | JumpLinks.story.vue | Not applicable | N/A | No jump-links pattern currently present. |
| 32 | Label.story.vue | Gap | `frontend/src/pages/WorkListPage.vue:679` | Replace custom status/progress chips with `pf-label`. |
| 33 | List.story.vue | Gap | `frontend/src/pages/WorkListPage.vue:667` | Replace generic list styling with PF list primitives where appropriate. |
| 34 | Masthead.story.vue | Gap | `frontend/src/layouts/ClientShell.vue:54` | Top bars are custom; migrate to `pf-masthead` primitives. |
| 35 | Menu.story.vue | Not applicable | N/A | No PF menu pattern currently implemented. |
| 36 | MenuToggle.story.vue | Not applicable | N/A | No PF menu-toggle currently in use. |
| 37 | Modal.story.vue | Used | `frontend/src/components/VlConfirmModal.vue:35` | Native confirms replaced by PF modal flow. |
| 38 | Navigation.story.vue | Gap | `frontend/src/layouts/SidebarNavigation.vue:43` | Custom nav structure should migrate to PF nav components. |
| 39 | NotificationBadge.story.vue | Gap | `frontend/src/layouts/AppShell.vue:208` | Replace custom notification count badge with `pf-notification-badge`. |
| 40 | NotificationDrawer.story.vue | Not applicable | N/A | No notification drawer interaction in current routes. |
| 41 | OverflowMenu.story.vue | Not applicable | N/A | No overflow menu pattern currently required. |
| 42 | Page.story.vue | Gap | `frontend/src/layouts/AppShell.vue:135` | App shell uses custom page framing; migrate to PF page layout primitives. |
| 43 | Pagination.story.vue | Not applicable | N/A | Current lists do not yet expose paginated UI controls. |
| 44 | Panel.story.vue | Not applicable | N/A | No panel component use case currently implemented. |
| 45 | Popover.story.vue | Not applicable | N/A | No popover interactions currently implemented. |
| 46 | Progress.story.vue | Gap | `frontend/src/pages/WorkListPage.vue:680` | Replace progress text chips with PF progress primitives. |
| 47 | ProgressStepper.story.vue | Not applicable | N/A | No stepper workflow UI currently present. |
| 48 | Radio.story.vue | Gap | `frontend/src/pages/WorkflowCreatePage.vue:193` | Replace native radios with PF radio primitives. |
| 49 | SearchInput.story.vue | Gap | `frontend/src/pages/WorkListPage.vue:619` | Replace native search input with `pf-search-input`. |
| 50 | Select-Typeahead.vue | Not applicable | N/A | Typeahead select behavior not implemented currently. |
| 51 | Select.story.vue | Gap | `frontend/src/pages/WorkListPage.vue:595` | Upgrade select controls to PF select components. |
| 52 | SimpleList.story.vue | Not applicable | N/A | No dedicated simple-list pattern currently required. |
| 53 | Skeleton.story.vue | Gap | `frontend/src/pages/WorkListPage.vue:657` | Replace text-only loading states with PF skeleton placeholders. |
| 54 | Spinner.story.vue | Gap | `frontend/src/pages/WorkListPage.vue:657` | Replace text-only loading states with PF spinner where applicable. |
| 55 | Switch.story.vue | Not applicable | N/A | No switch-style toggle currently required. |
| 56 | Table.story.vue | Used | `frontend/src/pages/NotificationDeliveryLogsPage.vue:127` | Raw tables remediated to PF table primitives across in-scope pages. |
| 57 | Tabs.story.vue | Not applicable | N/A | No tabbed layout currently in use. |
| 58 | TextInput.story.vue | Gap | `frontend/src/pages/WorkListPage.vue:619` | Replace native text inputs with PF text input primitives. |
| 59 | TextInputGroup.story.vue | Gap | `frontend/src/pages/OutputRunDetailPage.vue:377` | Replace custom grouped input action row with PF text-input-group. |
| 60 | Textarea.story.vue | Gap | `frontend/src/pages/TemplateDetailPage.vue:132` | Replace native textareas with PF textarea primitives. |
| 61 | Title.story.vue | Gap | `frontend/src/pages/WorkListPage.vue:583` | Replace ad-hoc page headings with PF title primitives. |
| 62 | ToggleGroup.story.vue | Not applicable | N/A | No toggle-group control currently implemented. |
| 63 | Toolbar.story.vue | Used | `frontend/src/pages/NotificationDeliveryLogsPage.vue:99` | PF toolbar adopted for filter/actions layout. |
| 64 | Tooltip.story.vue | Gap | `frontend/src/pages/NotificationSettingsPage.vue:481` | Add PF tooltip/help affordances for inline guidance where needed. |

## Post-remediation hard-gate proof (implemented)
- `frontend/src/components/VlConfirmModal.vue` introduces PatternFly modal confirmation flow.
- `frontend/src/pages/WorkListPage.vue` now uses modal confirmation for saved view delete and custom field archive.
- `frontend/src/pages/WorkflowEditPage.vue` now uses modal confirmation for stage/workflow delete.
- `frontend/src/pages/NotificationDeliveryLogsPage.vue`, `frontend/src/pages/NotificationSettingsPage.vue`, `frontend/src/pages/TemplatesPage.vue`, `frontend/src/pages/OutputRunDetailPage.vue`, `frontend/src/pages/OutputsPage.vue`, `frontend/src/pages/WorkflowCreatePage.vue`, `frontend/src/pages/WorkflowEditPage.vue`, `frontend/src/pages/TemplateDetailPage.vue` now use PF table primitives.

## Residual gap summary
Remaining PF component-adoption gaps are tracked directly in the matrix above (`Post status = Gap`) with file:line evidence and explicit remediation direction per component family.
