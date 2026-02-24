declare module "jordium-gantt-vue3" {
  import type { DefineComponent } from "vue";

  export type JordiumGanttLocale = "zh-CN" | "en-US";
  export type JordiumGanttTheme = "light" | "dark";
  export type JordiumGanttTimeScale = "hour" | "day" | "week" | "month" | "quarter" | "year";

  export interface JordiumGanttTask {
    id: number;
    name: string;
    startDate?: string;
    endDate?: string;
    progress?: number;
    predecessor?: number[] | string | string[];
    parentId?: number;
    children?: JordiumGanttTask[];
    collapsed?: boolean;
    isParent?: boolean;
    type?: string;
    description?: string;
    [key: string]: unknown;
  }

  export const GanttChart: DefineComponent<{
    tasks: JordiumGanttTask[];
    milestones?: JordiumGanttTask[];
    resources?: unknown[];
    viewMode?: "task" | "resource";
    showToolbar?: boolean;
    useDefaultDrawer?: boolean;
    useDefaultMilestoneDialog?: boolean;
    autoSortByStartDate?: boolean;
    allowDragAndResize?: boolean;
    enableTaskRowMove?: boolean;
    enableTaskListContextMenu?: boolean;
    enableTaskBarContextMenu?: boolean;
    taskListColumnRenderMode?: "default" | "declarative";
    taskListConfig?: unknown;
    locale?: JordiumGanttLocale;
    theme?: JordiumGanttTheme;
    timeScale?: JordiumGanttTimeScale;
    fullscreen?: boolean;
    expandAll?: boolean;
    enableLinkAnchor?: boolean;
    pendingTaskBackgroundColor?: string;
    delayTaskBackgroundColor?: string;
    completeTaskBackgroundColor?: string;
    ongoingTaskBackgroundColor?: string;
    showActualTaskbar?: boolean;
    enableTaskbarTooltip?: boolean;
    showConflicts?: boolean;
    showTaskbarTab?: boolean;
  }>;

  export const TaskListColumn: DefineComponent<{
    prop: string;
    label?: string;
    width?: number | string;
    align?: "left" | "center" | "right";
    cssClass?: string;
  }>;
}
