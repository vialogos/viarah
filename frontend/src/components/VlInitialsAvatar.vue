<script setup lang="ts">
import { computed } from "vue";

const props = withDefaults(
  defineProps<{
    label: string;
    src?: string | null;
    size?: "sm" | "md" | "lg" | "xl";
    bordered?: boolean;
  }>(),
  {
    src: null,
    size: "md",
    bordered: false,
  }
);

const COLOR_PALETTE = [
  "#1f4f8b", // blue
  "#3b5b9a", // indigo
  "#5a3e85", // purple
  "#8a2d4b", // red-ish
  "#8a4b1f", // orange-ish
  "#3a6b3a", // green
  "#2a6d7a", // teal
  "#4f4f4f", // grey
];

function hashString(input: string): number {
  let hash = 0;
  for (let i = 0; i < input.length; i += 1) {
    hash = (hash << 5) - hash + input.charCodeAt(i);
    hash |= 0;
  }
  return Math.abs(hash);
}

function initialsFor(label: string): string {
  const cleaned = (label || "").trim();
  if (!cleaned) {
    return "?";
  }

  const parts = cleaned
    .split(/\s+/)
    .map((p) => p.trim())
    .filter(Boolean);

  if (parts.length === 1) {
    return parts[0]!.slice(0, 2).toUpperCase();
  }

  const first = parts[0]!.slice(0, 1);
  const last = parts[parts.length - 1]!.slice(0, 1);
  return `${first}${last}`.toUpperCase();
}

function svgDataUrl(initials: string, background: string): string {
  const safeInitials = initials.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const svg = `<?xml version="1.0" encoding="UTF-8"?>\n` +
    `<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" viewBox="0 0 128 128" role="img" aria-label="${safeInitials}">` +
    `<rect width="128" height="128" rx="64" ry="64" fill="${background}"/>` +
    `<text x="64" y="68" text-anchor="middle" dominant-baseline="middle" font-family="system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif" font-size="52" font-weight="700" fill="#ffffff">${safeInitials}</text>` +
    `</svg>`;

  return `data:image/svg+xml,${encodeURIComponent(svg)}`;
}

const initials = computed(() => initialsFor(props.label));
const backgroundColor = computed(() => {
  const idx = hashString(props.label) % COLOR_PALETTE.length;
  const fallback = COLOR_PALETTE[0] ?? "#1f4f8b";
  return COLOR_PALETTE[idx] ?? fallback;
});

const dataUrl = computed(() => svgDataUrl(initials.value, backgroundColor.value));
const imageUrl = computed(() => props.src || dataUrl.value);
</script>

<template>
  <pf-avatar :src="imageUrl" :alt="props.label" :size="props.size" :bordered="props.bordered" />
</template>
