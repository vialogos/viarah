# PatternFly Vue component inventory (ViaRah)

This doc inventories the PatternFly Vue component catalog available in the ViaRah frontend and the **subset we need to implement/migrate** to satisfy `vialogos-labs/viarah#45` (Design System Refresh v1). It is intended to live in-repo under `docs/` so it can be referenced from MRs/issues.

## Context (versions + compatibility note)

ViaRah frontend dependencies (see `frontend/package.json`):

- `@patternfly/patternfly` `^6.4.0` (PF6 CSS + tokens)
- `@vue-patternfly/core` `^5.1.1` (Vue components catalog)

Important: `@vue-patternfly/core@5.1.1` currently renders **PatternFly v5** markup/classes (via `@patternfly/react-styles@5.x`), while issue `#45` requires **PF6** classnames (`pf-v6-*`) and consistency (no PF5/PF6 mixing). Treat the PF Vue catalog below as an API/coverage reference unless/until we align the component library to PF6.

## P0 (must-have for `#45`)

These are the components/patterns the current UI already uses (often as ad-hoc markup/CSS) and should be standardized behind PF6-aligned wrappers (recommended `Vl*` components) so we can apply consistent styling, accessibility, and deterministic selectors.

- **Button** (`PfButton`)
  - Needed across shells + pages for primary/secondary/plain/control/link variants, small sizing, danger states, disabled/in-progress, and icon buttons.
- **Card** (`PfCard`, `PfCardHeader`, `PfCardBody`, `PfCardFooter`, `PfCardTitle`, `PfCardActions`)
  - The UI heavily relies on a custom `.card` pattern; migrate to PF6 card markup or a `VlCard` wrapper to reduce bespoke CSS and improve hierarchy.
- **Title + text content** (`PfTitle`, `PfTextContent`, `PfText`, `PfTextList`)
  - Replace ad-hoc `.page-title` and free-form headings with consistent typography scales and spacing.
- **Form primitives** (`PfForm`, `PfFormGroup`, `PfFormSection`, `PfFormHelperText`, `PfHelperText`, `PfHelperTextItem`)
  - Central to “field guidance” acceptance criteria: add helper text/tooltips in settings + create/edit forms.
- **Inputs / selects / textareas**
  - `PfTextInput`, `PfTextarea`, plus either `PfFormSelect`/`PfFormSelectOption` (native select) or `PfSelect`/`PfSelectOption` (custom select).
- **Checkbox / radio / switch** (`PfCheckbox`, `PfRadio`, `PfSwitch`)
  - Used already in Work filters, visibility controls, and client approval/rejection flows.
- **Label / badge** (`PfLabel`, `PfBadge`, `PfNotificationBadge`)
  - Issue rules require `Label` for progress/workflow stage/GitLab labels, and `Badge` for counts.
  - `VlLabel` already exists; standardize the remaining badge patterns.
- **Alert** (`PfAlert`, `PfAlertActionLink`)
  - Used for warning states (e.g., missing workflow, unsafe actions).
- **Toolbar** (`PfToolbar`, `PfToolbarGroup`, `PfToolbarItem`, `PfToolbarFilter`)
  - Replace ad-hoc “toolbar rows” (Work list, Notifications) with consistent responsive layout + spacing.
- **Tooltip / popover** (`PfTooltip`, `PfPopover`)
  - Required to deliver “missing field descriptions/tooltips/help text” without cluttering forms.
- **Empty state + loading** (`PfEmptyState*`, `PfSpinner`, `PfSkeleton`)
  - Replace plain “Loading…” and “Select an org…” text blocks with consistent PF6 patterns.

## P1 (high-value next)

These unlock better information density and layout consistency across “workspace-heavy” pages, but aren’t strictly required to land the first pass.

- **Page layout + navigation** (`PfPage*`, `PfMasthead*`, `PfNav*`, `PfBreadcrumb*`)
  - Current shells (`AppShell.vue`, `ClientShell.vue`, `SidebarNavigation.vue`) are custom + Headless UI; migrating reduces one-off layout CSS and improves responsive behavior.
- **Panel / drawer (side detail surfaces)** (`PfPanel*`, `PfDrawer*`)
  - Useful for Work detail sidebars, metadata panels, and “peek” surfaces without full navigation.
- **Tabs** (`PfTabs`, `PfTab*`)
  - Useful for dense detail pages (Work detail, Output run detail, settings pages).
- **Data list** (`PfDataList*`, `PfDescriptionList*`, `PfList*`)
  - Replace ad-hoc `<ul>`/`<li>` list patterns with consistent spacing, alignment, and actions layout.
- **Pagination** (`PfPagination`, `PfPaginationOptionsMenu`)
  - Work list, SoWs list, Templates list, Outputs list as data grows.
- **Dropdown / menu** (`PfDropdown*`, `PfMenu*`, `PfMenuToggle*`, `PfOverflowMenu*`)
  - Standardize “row actions” and overflow actions without bespoke icon/button patterns.
- **Search input + input groups** (`PfSearchInput`, `PfInputGroup*`, `PfTextInputGroup*`)
  - Standardize search patterns and grouped inputs.
- **Progress visualization** (`PfProgress`, `PfProgressStepper`, `PfProgressStep`)
  - Complement `Label` for progress with an actual progress bar/stepper where appropriate.
- **Notification drawer** (`PfNotificationDrawer*`)
  - Convert notification lists to consistent PF patterns.

## P2 (optional / only if a page needs it)

- **File upload** (`PfFileUpload`)
- **Chip groups** (`PfChip`, `PfChipGroup`) — only for removable filter tokens (issue rules: don’t use `Chip` for status metadata).
- **Accordion / expandable section** (`PfAccordion*`, `PfExpandableSection*`) — for dense settings pages.
- **Hint** (`PfHint*`) — for inline guidance blocks inside forms.
- **Avatar / brand / background image** (`PfAvatar`, `PfBrand`, `PfBackgroundImage`)

## Page mapping (what to migrate where)

This is the current frontend surface list and the PatternFly components it most needs for `#45` compliance.

- `frontend/src/layouts/AppShell.vue`: `PfPage*`/`PfMasthead*`/`PfNav*` (P1), plus `PfToolbar` + `PfButton` + `PfBadge` patterns (P0).
- `frontend/src/layouts/ClientShell.vue`: `PfMasthead*`/`PfNav*` (P1), plus `PfButton` + `PfBadge` (P0).
- `frontend/src/layouts/SidebarNavigation.vue`: `PfNav*` + `PfNavExpandable` (P1) to replace custom disclosure/flyout behavior.
- `frontend/src/components/OrgProjectSwitcher.vue`: `PfFormGroup` + select + helper text (P0).
- `frontend/src/components/GitLabLinksCard.vue`: `PfCard*` + `PfFormGroup` + `PfTextInput` + `PfButton` + `PfLabel` (P0); consider `PfDataList*` for structured rows (P1).
- `frontend/src/pages/WorkListPage.vue`: `PfCard*` + `PfToolbar*` + `PfTextInput`/`PfSearchInput` + select + checkbox + labels (P0); consider `PfDataList*` + `PfPagination` (P1).
- `frontend/src/pages/WorkDetailPage.vue`: `PfCard*` + form primitives + alert + checkbox/select/textarea + labels (P0); consider `PfTabs` + `PfDrawer`/`PfPanel` (P1).
- `frontend/src/pages/NotificationsPage.vue`: `PfCard*` + `PfToolbar*` + form primitives (P0); consider `PfNotificationDrawer*` (P1).
- `frontend/src/pages/NotificationSettingsPage.vue`: form primitives + helper text + tooltips/popovers (P0); consider accordion/expandables for density (P2).
- `frontend/src/pages/NotificationDeliveryLogsPage.vue`: `PfCard*` + `PfToolbar*` + select + empty states (P0); consider pagination (P1).
- `frontend/src/pages/OutputsPage.vue`: `PfCard*` + form primitives + empty states (P0); consider `PfDataList*` + pagination (P1).
- `frontend/src/pages/OutputRunDetailPage.vue`: `PfCard*` + input groups (copy URL) + buttons + helper text (P0); consider tabs/panels (P1).
- `frontend/src/pages/TemplatesPage.vue`: `PfCard*` + form primitives + helper text (P0); consider data list + pagination (P1).
- `frontend/src/pages/TemplateDetailPage.vue`: `PfCard*` + textarea + helper text (P0).
- `frontend/src/pages/SowsPage.vue`: `PfCard*` + select + labels + empty states (P0); consider data list + pagination (P1).
- `frontend/src/pages/SowCreatePage.vue`: `PfForm*` + inputs/selects/textarea + helper text (P0).
- `frontend/src/pages/SowDetailPage.vue`: `PfCard*` + labels + actions (P0); consider tabs (P1).
- `frontend/src/pages/ProjectSettingsPage.vue`: `PfForm*` + select + helper text (P0).
- `frontend/src/pages/GitLabIntegrationSettingsPage.vue`: `PfForm*` + inputs + helper text + alerts (P0).
- `frontend/src/pages/WorkflowListPage.vue`: `PfCard*` + labels + buttons (P0); consider data list (P1).
- `frontend/src/pages/WorkflowCreatePage.vue`: `PfForm*` + inputs + helper text (P0).
- `frontend/src/pages/WorkflowEditPage.vue`: `PfForm*` + inputs + helper text (P0).
- `frontend/src/pages/LoginPage.vue`: `PfLoginPage` / `PfLogin*` (P1) or at minimum form primitives (P0).
- Client portal pages (`frontend/src/pages/Client*`): same P0 set (cards/forms/labels/buttons), plus optional P1 nav/page layout.

## Full catalog (installed `@vue-patternfly/core@5.1.1`)

Regenerate (from repo root):

```bash
python3 - <<'PY'
import pathlib, re
from collections import defaultdict

EXPORT_RE = re.compile(r"^export \\{ default as (Pf[^ ]+) \\} from '")
root = pathlib.Path("frontend/node_modules/@vue-patternfly/core/dist")

def collect(section: str) -> dict[str, list[str]]:
    base = root / section
    groups: dict[str, list[str]] = defaultdict(list)
    for path in sorted(base.rglob("index.d.ts")):
        group = "Base" if path.parent == base else str(path.parent.relative_to(base))
        for line in path.read_text(encoding="utf-8").splitlines():
            m = EXPORT_RE.match(line)
            if m:
                groups[group].append(m.group(1))
    return groups

for section in ["layouts", "components"]:
    print(f"## {section.title()} (from @vue-patternfly/core)")
    groups = collect(section)
    for group in ["Base"] + sorted(g for g in groups if g != "Base"):
        if group not in groups:
            continue
        print(f"\\n### {group}")
        for name in groups[group]:
            print(f"- {name}")
    print()
PY
```

### Layouts (from `@vue-patternfly/core`)

#### Base
- PfBullseye

#### Flex
- PfFlex
- PfFlexItem

#### Gallery
- PfGallery
- PfGalleryItem

#### Grid
- PfGrid
- PfGridItem

#### Level
- PfLevel
- PfLevelItem

#### Split
- PfSplit
- PfSplitItem

#### Stack
- PfStack
- PfStackItem

### Components (from `@vue-patternfly/core`)

#### Base
- PfAvatar
- PfBackdrop
- PfBackgroundImage
- PfBadge
- PfBanner
- PfBrand
- PfButton
- PfCheckbox
- PfCloseButton
- PfDivider
- PfFileUpload
- PfFormControlIcon
- PfIcon
- PfLabel
- PfNotificationBadge
- PfPopover
- PfProgress
- PfRadio
- PfSkeleton
- PfSpinner
- PfSwitch
- PfTextarea
- PfTextInput
- PfTitle

#### Accordion
- PfAccordion
- PfAccordionItem

#### ActionList
- PfActionList
- PfActionListGroup
- PfActionListItem

#### Alert
- PfAlert
- PfAlertActionLink
- PfAlertGroup
- PfAlertGroupInline
- PfAlertIcon

#### Breadcrumb
- PfBreadcrumb
- PfBreadcrumbItem

#### Card
- PfCard
- PfCardExpandableContent
- PfCardTitle
- PfCardBody
- PfCardFooter
- PfCardHeader
- PfCardHeaderMain
- PfCardActions

#### ChipGroup
- PfChip
- PfChipGroup

#### DataList
- PfDataList
- PfDataListAction
- PfDataListCell
- PfDataListCheck
- PfDataListContent
- PfDataListItem
- PfDataListItemRow
- PfDataListItemCells
- PfDataListToggle

#### DescriptionList
- PfDescriptionList
- PfDescriptionListDescription
- PfDescriptionListGroup
- PfDescriptionListTerm
- PfDescriptionListTermHelpText
- PfDescriptionListTermHelpTextButton

#### Drawer
- PfDrawer
- PfDrawerActions
- PfDrawerCloseButton
- PfDrawerContent
- PfDrawerContentBody
- PfDrawerHead
- PfDrawerMain
- PfDrawerPanelBody
- PfDrawerPanelContent
- PfDrawerSection

#### Dropdown
- PfDropdown
- PfDropdownGroup
- PfDropdownItem
- PfDropdownList

#### EmptyState
- PfEmptyState
- PfEmptyStateBody
- PfEmptyStateFooter
- PfEmptyStateHeader
- PfEmptyStateIcon
- PfEmptyStateActions

#### ExpandableSection
- PfExpandableSection
- PfExpandableSectionToggle

#### Form
- PfForm
- PfFormAlert
- PfFormGroup
- PfFormFieldGroup
- PfFormFieldGroupHeader
- PfFormHelperText
- PfFormSection
- PfActionGroup

#### FormSelect
- PfFormSelect
- PfFormSelectOption

#### HelperText
- PfHelperText
- PfHelperTextItem

#### Hint
- PfHint
- PfHintBody
- PfHintFooter
- PfHintTitle

#### InputGroup
- PfInputGroup
- PfInputGroupItem
- PfInputGroupText

#### JumpLinks
- PfJumpLinks
- PfJumpLinksItem
- PfJumpLinksList

#### List
- PfList
- PfListItem

#### LoginPage
- PfLogin
- PfLoginFooter
- PfLoginMainFooter
- PfLoginMainFooterBandItem
- PfLoginMainFooterLinksItem
- PfLoginHeader
- PfLoginMainHeader
- PfLoginMainBody
- PfLoginPage

#### Masthead
- PfMasthead
- PfMastheadBrand
- PfMastheadContent
- PfMastheadMain
- PfMastheadToggle

#### Menu
- PfMenu
- PfMenuBreadcrumb
- PfMenuContent
- PfMenuFooter
- PfMenuGroup
- PfMenuInput
- PfMenuItem
- PfMenuItemAction
- PfMenuList

#### MenuToggle
- PfMenuToggle
- PfMenuToggleCheckbox
- PfMenuToggleAction

#### Modal
- PfModal
- PfModalHeader

#### Nav
- PfNav
- PfNavList
- PfNavGroup
- PfNavItem
- PfNavItemSeparator
- PfNavExpandable

#### NotificationDrawer
- PfNotificationDrawer
- PfNotificationDrawerHeader
- PfNotificationDrawerBody
- PfNotificationDrawerList
- PfNotificationDrawerListItem
- PfNotificationDrawerListItemHeader
- PfNotificationDrawerListItemBody
- PfNotificationDrawerGroup
- PfNotificationDrawerGroupList

#### OverflowMenu
- PfOverflowMenu
- PfOverflowMenuContent
- PfOverflowMenuControl
- PfOverflowMenuGroup
- PfOverflowMenuItem
- PfOverflowMenuDropdownItem

#### Page
- PfPage
- PfPageBreadcrumb
- PfPageGroup
- PfPageNavigation
- PfPageSidebar
- PfPageSidebarBody
- PfPageSection
- PfPageToggleButton

#### Pagination
- PfPagination
- PfPaginationOptionsMenu
- PfNavigation

#### Panel
- PfPanel
- PfPanelMain
- PfPanelMainBody
- PfPanelHeader
- PfPanelFooter

#### ProgressStepper
- PfProgressStepper
- PfProgressStep

#### SearchInput
- PfSearchInput
- PfAdvancedSearchMenu

#### Select
- PfSelect
- PfSelectGroup
- PfSelectList
- PfSelectOption

#### SimpleList
- PfSimpleList
- PfSimpleListGroup
- PfSimpleListItem

#### Tabs
- PfTabs
- PfTab
- PfTabButton
- PfTabContent
- PfTabTitleText
- PfTabTitleIcon

#### Text
- PfTextContent
- PfText
- PfTextList
- PfTextListItem

#### TextInputGroup
- PfTextInputGroup
- PfTextInputGroupMain
- PfTextInputGroupUtilities

#### ToggleGroup
- PfToggleGroup
- PfToggleGroupItem

#### Toolbar
- PfToolbar
- PfToolbarChipGroupContent
- PfToolbarGroup
- PfToolbarItem
- PfToolbarContent
- PfToolbarExpandableContent
- PfToolbarToggleGroup
- PfToolbarFilter

#### Tooltip
- PfTooltip
- PfTooltipArrow
- PfTooltipContent
