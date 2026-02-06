<script setup lang="ts">
import { computed } from "vue";
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
</script>

<template>
  <nav class="sidebar-nav" :class="{ collapsed: props.collapsed }" aria-label="Internal navigation">
    <template v-if="props.collapsed">
      <section v-for="group in props.groups" :key="group.id" class="rail-group">
        <RouterLink
          v-for="item in group.items"
          :key="item.id"
          class="nav-link rail-link"
          :class="{ active: itemIsActive(item) }"
          :to="item.to"
          :aria-label="`${group.label}: ${item.label}`"
          :title="`${group.label}: ${item.label}`"
          @click="emit('navigate')"
        >
          <component :is="shellIconMap[item.icon]" class="icon icon-item" aria-hidden="true" />
          <span class="sr-only">{{ item.label }}</span>
          <span class="rail-tooltip">{{ group.label }}: {{ item.label }}</span>
        </RouterLink>
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
  background: #f9fafb;
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
  background: #f3f4f6;
}

.group-trigger.active {
  background: #eff6ff;
  color: var(--accent);
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
  background: #eef2ff;
  border-color: #c7d2fe;
  text-decoration: none;
}

.nav-link.active {
  background: #e0e7ff;
  border-color: #93c5fd;
  color: #1d4ed8;
  box-shadow: inset 3px 0 0 #1d4ed8;
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
  position: relative;
}

.rail-link.active {
  background: #dbeafe;
  border-color: #60a5fa;
  color: #1d4ed8;
  box-shadow: inset 3px 0 0 #1d4ed8;
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

.rail-link:hover .rail-tooltip,
.rail-link:focus-visible .rail-tooltip {
  opacity: 1;
  transform: translateY(-50%) translateX(0);
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
