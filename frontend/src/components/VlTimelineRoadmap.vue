<script setup lang="ts">
/**
 * VlTimelineRoadmap
 *
 * Wrapper around `vis-timeline` for the /timeline roadmap page.
 *
 * - Owns the Timeline instance lifecycle (mount/destroy).
 * - Accepts items/groups from the parent and syncs on change.
 * - Emits hover/select/open events (parent decides what to do).
 * - Enables vis-timeline XSS filtering to avoid unsafe HTML injection via item content.
 */
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import {
  type DataItem,
  Timeline,
  type TimelineGroup,
  type TimelineOptions,
  type TimelineTimeAxisScaleType,
} from "vis-timeline/standalone";

import "vis-timeline/styles/vis-timeline-graph2d.min.css";

const props = withDefaults(
  defineProps<{
    items: DataItem[];
    groups: TimelineGroup[];
    timeAxisScale: TimelineTimeAxisScaleType;
    ariaLabel?: string;
  }>(),
  {
    ariaLabel: "Timeline roadmap",
  }
);

const emit = defineEmits<{
  (e: "hover", itemId: string | null): void;
  (e: "select", itemId: string | null): void;
  (e: "open", itemId: string): void;
}>();

const containerEl = ref<HTMLElement | null>(null);
let timeline: Timeline | null = null;

function getTimeline(): Timeline | null {
  return timeline;
}

function fit(): void {
  const tl = getTimeline();
  if (!tl) {
    return;
  }
  tl.fit({ animation: { duration: 250 } });
}

function zoomIn(): void {
  const tl = getTimeline();
  if (!tl) {
    return;
  }
  tl.zoomIn(0.2, { animation: { duration: 250 } });
}

function zoomOut(): void {
  const tl = getTimeline();
  if (!tl) {
    return;
  }
  tl.zoomOut(0.2, { animation: { duration: 250 } });
}

function setWindow(start: Date, end: Date): void {
  const tl = getTimeline();
  if (!tl) {
    return;
  }
  tl.setWindow(start, end, { animation: { duration: 250 } });
}

function syncOptions(): void {
  const tl = getTimeline();
  if (!tl) {
    return;
  }
  tl.setOptions({ timeAxis: { scale: props.timeAxisScale, step: 1 } });
}

function syncData(): void {
  const tl = getTimeline();
  if (!tl) {
    return;
  }
  tl.setData({ items: props.items, groups: props.groups });
}

defineExpose({ fit, zoomIn, zoomOut, setWindow });

onMounted(() => {
  if (!containerEl.value) {
    return;
  }

  const options: TimelineOptions = {
    autoResize: true,
    selectable: true,
    multiselect: false,
    zoomable: true,
    verticalScroll: true,
    orientation: { axis: "top" },
    margin: { axis: 8, item: 10 },
    xss: { disabled: false },
    timeAxis: { scale: props.timeAxisScale, step: 1 },
  };

  timeline = new Timeline(containerEl.value, props.items, props.groups, options);
  timeline.on("itemover", (evt: { item?: string | number | null }) => {
    emit("hover", evt.item == null ? null : String(evt.item));
  });
  timeline.on("itemout", () => emit("hover", null));
  timeline.on("select", (evt: { items?: Array<string | number> }) => {
    const id = evt.items && evt.items.length > 0 ? evt.items[0] : null;
    emit("select", id == null ? null : String(id));
  });
  timeline.on("doubleClick", (evt: { item?: string | number | null }) => {
    if (evt.item != null) {
      emit("open", String(evt.item));
    }
  });
});

onBeforeUnmount(() => {
  timeline?.destroy();
  timeline = null;
});

watch(() => props.timeAxisScale, () => syncOptions());
watch(() => props.items, () => syncData());
watch(() => props.groups, () => syncData());
</script>

<template>
  <div ref="containerEl" class="vl-timeline-roadmap" :aria-label="ariaLabel" />
</template>

<style scoped>
.vl-timeline-roadmap {
  height: min(62vh, 520px);
  min-height: 360px;
  border: 1px solid var(--border);
  border-radius: 12px;
  overflow: hidden;
  background: var(--surface, #fff);
}

:deep(.vis-item.vl-timeline-item) {
  border-radius: 999px;
  border-width: 1px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

:deep(.vis-item.vl-timeline-item--backlog) {
  background: #dbeafe;
  border-color: #93c5fd;
  color: #1e3a8a;
}

:deep(.vis-item.vl-timeline-item--in-progress) {
  background: #ffedd5;
  border-color: #fdba74;
  color: #7c2d12;
}

:deep(.vis-item.vl-timeline-item--qa) {
  background: #ede9fe;
  border-color: #c4b5fd;
  color: #4c1d95;
}

:deep(.vis-item.vl-timeline-item--done) {
  background: #dcfce7;
  border-color: #86efac;
  color: #14532d;
}
</style>
