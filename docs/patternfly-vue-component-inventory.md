# PatternFly Vue Component Inventory and Coverage Matrix (Issue #45)

## Scope and method
- Upstream component stories read in full from: `https://github.com/mtorromeo/vue-patternfly/tree/main/apps/docs/src/stories/Components`
- Read proof artifact (all 64 files, sha256 + line counts): `docs/patternfly-vue-story-read-proof-20260211.txt`
- Baseline (before this completion pass): `33` applicable gaps
- Final (after remediation): `0` applicable gaps

## Version-selection rationale (internet-verified)
Command outputs:
```text
$ npm view @vue-patternfly/core dist-tags
{ latest: '5.1.1' }

$ npm view @vue-patternfly/table dist-tags
{ latest: '6.0.0-alpha.1' }

$ npm ls @vue-patternfly/core @vue-patternfly/table @patternfly/patternfly --depth=0
frontend@0.0.0 /home/oscar/ViaLogos/viarah/code/.worktrees/viarah/mr-39/frontend
├── @patternfly/patternfly@6.4.0
├── @vue-patternfly/core@6.0.0-beta.7
└── @vue-patternfly/table@6.0.0-alpha.1

$ npm view @vue-patternfly/table@6.0.0-alpha.1 peerDependencies
{ '@vueuse/core': '^13', '@vue-patternfly/core': '^6.0.0-beta.1' }

$ npm view @vue-patternfly/table@5.0.0 peerDependencies
{ '@vueuse/core': '^13', '@vue-patternfly/core': '^5.0.0' }
```
Decision:
- Use `@vue-patternfly/core@^6.0.0-beta.7` with `@vue-patternfly/table@^6.0.0-alpha.1`.
- Reason: full component-parity implementation for #45 required the newest table line, and the newest table line peers against core v6 beta.
- Note: `@vue-patternfly/table@6.0.0-alpha.1` exports `./style.css` but package content currently ships `dist/table.css`; build is stable without importing package CSS because PatternFly base CSS is already imported.

References:
- https://www.npmjs.com/package/@vue-patternfly/core?activeTab=versions
- https://www.npmjs.com/package/@vue-patternfly/table?activeTab=versions
- https://github.com/mtorromeo/vue-patternfly/blob/main/apps/docs/src/stories/Components/Table.story.vue
- https://github.com/mtorromeo/vue-patternfly/blob/main/apps/docs/src/stories/Components/FormSelect.story.vue

## Hard-gate proof (raw tables + native confirm + chip/badge ban)
```text
$ rg -n "<table|window\.confirm|\bconfirm\(" frontend/src -g '*.vue' -g '*.ts' -g '*.js'
# no matches

$ rg -n "class=\"(chip|badge)\"|\.chip\b|\.badge\b" frontend/src
# no matches
```

## Full 64-story coverage matrix (final)
Legend:
- `Used`: component family is actively used in ViaRah UI.
- `Not applicable`: no current route-level interface need for this component family.

| # | Story file | Final status | Evidence (file:line) | Rationale |
|---|---|---|---|---|
| 1 | Accordion.story.vue | Not applicable | N/A | No accordion interaction exists in current routes. |
| 2 | ActionList.story.vue | Not applicable | N/A | No action-list layout pattern in product scope. |
| 3 | Alert.story.vue | Used | `frontend/src/pages/WorkListPage.vue:706` | Error/warning/info surfaces use PF alerts. |
| 4 | Avatar.story.vue | Used | `frontend/src/components/VlInitialsAvatar.vue:78` | Team directory cards use avatars (initials SVG). |
| 5 | BackgroundImage.iframe.vue | Not applicable | N/A | Story helper artifact, not a product UI primitive. |
| 6 | BackgroundImage.story.vue | Not applicable | N/A | No route uses hero/background-image treatment. |
| 7 | Badge.story.vue | Not applicable | N/A | No badge use-cases in current UI; semantic tags use PF labels (`VlLabel`) and counts use PF notification-badge. |
| 8 | Banner.story.vue | Not applicable | N/A | No banner announcement strip requirement in current UX. |
| 9 | Brand.story.vue | Used | `frontend/src/layouts/AppShell.vue:82` | PF brand primitive used in shell masthead. |
| 10 | Breadcrumb.story.vue | Not applicable | N/A | No breadcrumb navigation in existing IA. |
| 11 | Button.story.vue | Used | `frontend/src/components/VlConfirmModal.vue:38` | PF button primitives used in modal and forms. |
| 12 | Card.story.vue | Used | `frontend/src/pages/WorkListPage.vue:624` | PF card primitives replace custom card containers. |
| 13 | Checkbox.story.vue | Used | `frontend/src/pages/WorkListPage.vue:665` | PF checkbox used for filters/settings/field toggles. |
| 14 | Chip.story.vue | Not applicable | N/A | No removable/filter-chip UX required; semantic tags are labels. |
| 15 | CloseButton.story.vue | Used | `frontend/src/pages/OutputRunDetailPage.vue:391` | PF close-button used for dismiss action. |
| 16 | Content.story.vue | Used | `frontend/src/pages/WorkListPage.vue:610` | Rich text blocks use PF content primitives. |
| 17 | DataList.story.vue | Used | `frontend/src/pages/WorkListPage.vue:718` | Task/field lists migrated to PF data-list. |
| 18 | DescriptionList.story.vue | Used | `frontend/src/pages/OutputRunDetailPage.vue:365` | Metadata stacks use PF description-list. |
| 19 | Divider.story.vue | Not applicable | N/A | No explicit divider component need after layout migration. |
| 20 | Drawer.story.vue | Not applicable | N/A | No drawer interaction in current route set. |
| 21 | Dropdown.story.vue | Not applicable | N/A | No contextual dropdown action menus in current scope. |
| 22 | EmptyState.story.vue | Used | `frontend/src/pages/WorkListPage.vue:614` | Empty/select-required states use PF empty-state. |
| 23 | ExpandableSection.story.vue | Used | `frontend/src/components/TrustPanel.vue:68` | Progressive disclosure for trust-panel details uses PF expandable-section. |
| 24 | FileUpload.story.vue | Used | `frontend/src/pages/WorkDetailPage.vue:941` | Task attachments uploader uses PF file-upload to select and upload a single file. |
| 25 | Form.story.vue | Used | `frontend/src/pages/WorkListPage.vue:626` | Forms migrated to PF form/form-group primitives. |
| 26 | FormSelect.story.vue | Used | `frontend/src/pages/WorkListPage.vue:629` | Native selects replaced by PF form-select for simple choices. |
| 27 | HelperText.story.vue | Used | `frontend/src/pages/NotificationSettingsPage.vue:484` | Inline guidance uses PF helper-text. |
| 28 | Hint.story.vue | Not applicable | N/A | No dedicated hint card pattern in routes. |
| 29 | Icon.story.vue | Used | `frontend/src/layouts/AppShell.vue:93` | Icons wrapped through PF icon primitive. |
| 30 | InputGroup.story.vue | Used | `frontend/src/pages/OutputRunDetailPage.vue:465` | Grouped datetime input/action row uses PF input-group. |
| 31 | JumpLinks.story.vue | Not applicable | N/A | No jump-link navigation pattern in current UX. |
| 32 | Label.story.vue | Used | `frontend/src/components/VlLabel.vue:19` | Task/status/progress tags use PF labels. |
| 33 | List.story.vue | Used | `frontend/src/pages/WorkListPage.vue:764` | Subtask stacks use PF list/list-item primitives. |
| 34 | Masthead.story.vue | Used | `frontend/src/layouts/AppShell.vue:76` | App/client shells now use PF masthead primitives. |
| 35 | Menu.story.vue | Not applicable | N/A | No PF menu component requirement in current routes. |
| 36 | MenuToggle.story.vue | Not applicable | N/A | No menu-toggle requirement without PF menu usage. |
| 37 | Modal.story.vue | Used | `frontend/src/components/VlConfirmModal.vue:35` | Confirm flows use PF modal; native confirm removed. |
| 38 | Navigation.story.vue | Used | `frontend/src/layouts/SidebarNavigation.vue:29` | Shell navigation migrated to PF nav primitives. |
| 39 | NotificationBadge.story.vue | Used | `frontend/src/layouts/AppShell.vue:91` | Notification counters use PF notification-badge. |
| 40 | NotificationDrawer.story.vue | Not applicable | N/A | No notification drawer panel in product scope. |
| 41 | OverflowMenu.story.vue | Not applicable | N/A | No overflow-menu pattern required by current IA. |
| 42 | Page.story.vue | Used | `frontend/src/layouts/AppShell.vue:74` | Layout framing migrated to PF page primitives. |
| 43 | Pagination.story.vue | Not applicable | N/A | No paginated list controls exposed in UI today. |
| 44 | Panel.story.vue | Not applicable | N/A | No panel component use-case in current screens. |
| 45 | Popover.story.vue | Not applicable | N/A | No popover interaction requirement currently. |
| 46 | Progress.story.vue | Used | `frontend/src/pages/WorkListPage.vue:737` | Task/subtask progress uses PF progress component. |
| 47 | ProgressStepper.story.vue | Not applicable | N/A | No stepper workflow visualization in current scope. |
| 48 | Radio.story.vue | Used | `frontend/src/pages/WorkflowCreatePage.vue:192` | Done-stage selection uses PF radio controls. |
| 49 | SearchInput.story.vue | Used | `frontend/src/pages/WorkListPage.vue:655` | Task filtering uses PF search-input. |
| 50 | Select-Typeahead.vue | Not applicable | N/A | No typeahead-select UX requirement in product routes. |
| 51 | Select.story.vue | Not applicable | N/A | Product uses simple static selects; PF form-select is the correct primitive per docs guidance. |
| 52 | SimpleList.story.vue | Not applicable | N/A | No simple-list-only interface requirement. |
| 53 | Skeleton.story.vue | Used | `frontend/src/pages/WorkListPage.vue:702` | Loading placeholders use PF skeleton. |
| 54 | Spinner.story.vue | Used | `frontend/src/pages/WorkListPage.vue:701` | Loading indicators use PF spinner. |
| 55 | Switch.story.vue | Not applicable | N/A | No switch-style toggle requirement in current UX. |
| 56 | Table.story.vue | Used | `frontend/src/pages/NotificationDeliveryLogsPage.vue:134` | All in-scope raw tables migrated to PF table primitives. |
| 57 | Tabs.story.vue | Used | `frontend/src/components/team/TeamPersonModal.vue:719` | Team Person modal uses tabs for editable sections. |
| 58 | TextInput.story.vue | Used | `frontend/src/pages/TemplatesPage.vue:174` | Text inputs migrated to PF text-input primitives. |
| 59 | TextInputGroup.story.vue | Used | `frontend/src/pages/OutputRunDetailPage.vue:387` | Token/share URL row uses PF text-input-group. |
| 60 | Textarea.story.vue | Used | `frontend/src/pages/TemplateDetailPage.vue:132` | Textareas migrated to PF textarea primitive. |
| 61 | Title.story.vue | Used | `frontend/src/pages/WorkListPage.vue:609` | Page/section headings use PF title. |
| 62 | ToggleGroup.story.vue | Not applicable | N/A | No toggle-group control requirement in current routes. |
| 63 | Toolbar.story.vue | Used | `frontend/src/layouts/AppShell.vue:87` | Shell action bars and filters use PF toolbar. |
| 64 | Tooltip.story.vue | Used | `frontend/src/pages/NotificationSettingsPage.vue:528` | Inline help affordances use PF tooltip. |

## Final gap summary
- Applicable gaps remaining: `0`
- Any non-`Used` rows are `Not applicable` and tied to concrete route/product-scope rationale above.
