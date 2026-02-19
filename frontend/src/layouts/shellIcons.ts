import type { Component } from "vue";
import {
  Bell,
  Boxes,
  Briefcase,
  Building2,
  CalendarRange,
  ChartGantt,
  FilePlus2,
  Files,
  FolderOpen,
  GitBranch,
  LayoutDashboard,
  ScrollText,
  Settings,
  SlidersHorizontal,
  Sparkles,
  Users,
  Workflow,
} from "lucide-vue-next";

import type { ShellNavIconName } from "./appShellNav";

export const shellIconMap: Record<ShellNavIconName, Component> = {
  dashboard: LayoutDashboard,
  work: Briefcase,
  timeline: CalendarRange,
  gantt: ChartGantt,
  projects: FolderOpen,
  clients: Building2,
  team: Users,
  templates: Files,
  outputs: Boxes,
  sows: ScrollText,
  notifications: Bell,
  settings: Settings,
  workflow: Workflow,
  project: SlidersHorizontal,
  integration: GitBranch,
  sparkles: Sparkles,
  "quick-add": FilePlus2,
};
