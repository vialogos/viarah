<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { Disclosure, DisclosureButton, DisclosurePanel } from "@headlessui/vue";
import { ChevronDown } from "lucide-vue-next";

import { isShellNavItemActive, type ShellNavGroup, type ShellNavItem } from "./appShellNav";
import { shellIconMap } from "./shellIcons";

const props = withDefaults(
  defineProps<{
    groups: ShellNavGroup[];
    collapsed?: boolean;
  }>(),
  {
    collapsed: false,
  }
);

const emit = defineEmits<{
  (event: "navigate"): void;
}>();

const route = useRoute();
const collapsedNavRef = ref<HTMLElement | null>(null);
const openRailGroupId = ref<string | null>(null);

const groupsWithState = computed(() =>
  props.groups.map((group) => {
    const hasActiveItem = group.items.some((item) => isShellNavItemActive(item, route.path));
    return {
      ...group,
      hasActiveItem,
      isOpenByDefault: group.defaultExpanded || hasActiveItem,
    };
  })
);

function itemIsActive(item: ShellNavItem): boolean {
  return isShellNavItemActive(item, route.path);
}

function closeRailFlyout(): void {
  openRailGroupId.value = null;
}

function railFlyoutId(groupId: string): string {
  return `rail-flyout-${groupId}`;
}

function isRailGroupOpen(groupId: string): boolean {
  return openRailGroupId.value === groupId;
}

function toggleRailGroup(groupId: string): void {
  openRailGroupId.value = openRailGroupId.value === groupId ? null : groupId;
}

function handleDocumentPointerDown(event: MouseEvent): void {
  if (!props.collapsed || !collapsedNavRef.value) {
    return;
  }

  const target = event.target;
  if (!(target instanceof Node)) {
    return;
  }

  if (!collapsedNavRef.value.contains(target)) {
    closeRailFlyout();
  }
}

function handleDocumentKeydown(event: KeyboardEvent): void {
  if (event.key === "Escape") {
    closeRailFlyout();
  }
}

watch(
  () => route.fullPath,
  () => {
    closeRailFlyout();
  }
);

watch(
  () => props.collapsed,
  (collapsed) => {
    if (!collapsed) {
      closeRailFlyout();
    }
  }
);

onMounted(() => {
  document.addEventListener("mousedown", handleDocumentPointerDown);
  document.addEventListener("keydown", handleDocumentKeydown);
});

onUnmounted(() => {
  document.removeEventListener("mousedown", handleDocumentPointerDown);
  document.removeEventListener("keydown", handleDocumentKeydown);
});
</script>

<template>
  <nav ref="collapsedNavRef" class="sidebar-nav" :class="{ collapsed: props.collapsed }" aria-label="Internal navigation">
    <template v-if="props.collapsed">
      <section
        v-for="group in groupsWithState"
        :key="group.id"
        class="rail-group rail-parent-group"
        :class="{ active: group.hasActiveItem }"
      >
        <button
          type="button"
          class="nav-link rail-link rail-parent-link"
          :class="{ active: group.hasActiveItem, open: isRailGroupOpen(group.id) }"
          :aria-label="`${group.label} menu`"
          :title="`${group.label} menu`"
          :aria-expanded="isRailGroupOpen(group.id) ? 'true' : 'false'"
          :aria-controls="railFlyoutId(group.id)"
          @click="toggleRailGroup(group.id)"
        >
          <component :is="shellIconMap[group.icon]" class="icon icon-group" aria-hidden="true" />
          <span class="sr-only">{{ group.label }}</span>
          <span class="rail-tooltip">{{ group.label }}</span>
        </button>

        <div
          v-if="group.items.length > 0"
          :id="railFlyoutId(group.id)"
          class="rail-flyout"
          :class="{ open: isRailGroupOpen(group.id) }"
          :aria-label="`${group.label} submenu`"
        >
          <RouterLink
            v-for="item in group.items"
            :key="item.id"
            class="rail-flyout-link"
            :class="{ active: itemIsActive(item) }"
            :to="item.to"
            @click="
              closeRailFlyout();
              emit('navigate');
            "
          >
            <component :is="shellIconMap[item.icon]" class="icon icon-item" aria-hidden="true" />
            <span>{{ item.label }}</span>
          </RouterLink>
        </div>
      </section>
    </template>

    <template v-else>
      <Disclosure
        v-for="group in groupsWithState"
        :key="group.id"
        v-slot="{ open }"
        as="section"
        class="nav-group"
        :default-open="group.isOpenByDefault"
      >
        <DisclosureButton class="group-trigger" :class="{ active: group.hasActiveItem }">
          <span class="group-title">
            <component :is="shellIconMap[group.icon]" class="icon icon-group" aria-hidden="true" />
            {{ group.label }}
          </span>
          <ChevronDown class="icon icon-chevron" :class="{ open }" aria-hidden="true" />
        </DisclosureButton>

        <DisclosurePanel class="group-items">
          <RouterLink
            v-for="item in group.items"
            :key="item.id"
            class="nav-link"
            :class="{ active: itemIsActive(item) }"
            :to="item.to"
            @click="emit('navigate')"
          >
            <component :is="shellIconMap[item.icon]" class="icon icon-item" aria-hidden="true" />
            <span>{{ item.label }}</span>
          </RouterLink>
        </DisclosurePanel>
      </Disclosure>
    </template>
  </nav>
</template>

<style scoped>
.sidebar-nav {
  display: flex;
  flex-direction: column;
  gap: 0.55rem;
}

.nav-group {
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--pf-t--global--background--color--control--default);
}

.group-trigger {
  border: 0;
  border-radius: 12px;
  width: 100%;
  background: transparent;
  color: var(--text);
  padding: 0.6rem 0.7rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  font-weight: 600;
}

.group-trigger:hover {
  background: var(--pf-t--global--background--color--control--default);
}

.group-trigger.active {
  background: var(--pf-t--global--background--color--control--default);
  color: var(--pf-t--global--text--color--brand--default);
}

.group-title {
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
}

.group-items {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  padding: 0 0.55rem 0.55rem;
}

.nav-link {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  border-radius: 10px;
  border: 1px solid transparent;
  padding: 0.5rem 0.6rem;
  color: var(--text);
  text-decoration: none;
  font-weight: 500;
}

.nav-link:hover {
  background: var(--pf-t--global--background--color--control--default);
  border-color: var(--pf-t--global--border--color--hover);
  text-decoration: none;
}

.nav-link.active {
  background: var(--pf-t--global--background--color--control--default);
  border-color: var(--pf-t--global--border--color--clicked);
  color: var(--pf-t--global--text--color--brand--default);
  box-shadow: inset 3px 0 0 var(--pf-t--global--border--color--clicked);
  font-weight: 600;
}

.icon {
  width: 1rem;
  height: 1rem;
  flex-shrink: 0;
}

.icon-chevron {
  transition: transform 120ms ease;
}

.icon-chevron.open {
  transform: rotate(180deg);
}

.sidebar-nav.collapsed {
  gap: 0.35rem;
}

.rail-group {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  padding-top: 0.35rem;
  border-top: 1px solid var(--border);
}

.rail-group:first-child {
  border-top: 0;
  padding-top: 0;
}

.rail-link {
  justify-content: center;
  padding: 0.55rem;
  width: 100%;
  cursor: pointer;
  position: relative;
}

.rail-parent-group {
  position: relative;
}

.rail-parent-link.active {
  background: var(--pf-t--global--background--color--control--default);
  border-color: var(--pf-t--global--border--color--clicked);
  color: var(--pf-t--global--text--color--brand--default);
  box-shadow: inset 3px 0 0 var(--pf-t--global--border--color--clicked);
}

.rail-parent-link.open {
  border-color: var(--pf-t--global--border--color--clicked);
}

.rail-tooltip {
  position: absolute;
  left: calc(100% + 0.45rem);
  top: 50%;
  transform: translateY(-50%) translateX(-4px);
  opacity: 0;
  pointer-events: none;
  z-index: 30;
  white-space: nowrap;
  border-radius: 8px;
  border: 1px solid #334155;
  background: #0f172a;
  color: #f8fafc;
  font-size: 0.75rem;
  font-weight: 500;
  line-height: 1;
  padding: 0.35rem 0.5rem;
  transition: opacity 140ms ease, transform 140ms ease;
}

.rail-parent-group:hover .rail-tooltip,
.rail-parent-group:focus-within .rail-tooltip {
  opacity: 1;
  transform: translateY(-50%) translateX(0);
}

.rail-flyout {
  position: absolute;
  left: calc(100% + 0.55rem);
  top: 50%;
  transform: translateY(-50%) translateX(-6px);
  opacity: 0;
  pointer-events: none;
  visibility: hidden;
  z-index: 35;
  min-width: 220px;
  border-radius: 12px;
  border: 1px solid var(--border);
  background: var(--panel);
  box-shadow: var(--pf-t--global--box-shadow--lg);
  padding: 0.45rem;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  transition: opacity 140ms ease, transform 140ms ease;
}

.rail-flyout.open {
  opacity: 1;
  transform: translateY(-50%) translateX(0);
  pointer-events: auto;
  visibility: visible;
}

.rail-flyout-link {
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  border-radius: 9px;
  border: 1px solid transparent;
  padding: 0.45rem 0.5rem;
  color: var(--text);
  text-decoration: none;
  font-size: 0.88rem;
  font-weight: 500;
}

.rail-flyout-link:hover {
  background: var(--pf-t--global--background--color--control--default);
  border-color: var(--pf-t--global--border--color--hover);
  text-decoration: none;
}

.rail-flyout-link.active {
  background: var(--pf-t--global--background--color--control--default);
  border-color: var(--pf-t--global--border--color--clicked);
  color: var(--pf-t--global--text--color--brand--default);
  font-weight: 600;
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
</style>
