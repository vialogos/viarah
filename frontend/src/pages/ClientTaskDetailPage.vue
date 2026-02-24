<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api, ApiError } from "../api";
import type { Comment, Task } from "../api/types";
import VlLabel from "../components/VlLabel.vue";
import { useContextStore } from "../stores/context";
import { useSessionStore } from "../stores/session";
import { formatTimestamp } from "../utils/format";
import { taskStatusLabelColor, workItemStatusLabel } from "../utils/labels";

const props = defineProps<{ taskId: string }>();

const router = useRouter();
const route = useRoute();
const session = useSessionStore();
const context = useContextStore();

const task = ref<Task | null>(null);
const comments = ref<Comment[]>([]);
const loading = ref(false);
const error = ref("");
const collabError = ref("");
const commentDraft = ref("");
const posting = ref(false);

const projectName = computed(() => {
  if (!context.projectId) {
    return "";
  }
  return context.projects.find((p) => p.id === context.projectId)?.name ?? "";
});

async function handleUnauthorized() {
  session.clearLocal("unauthorized");
  await router.push({ path: "/login", query: { redirect: route.fullPath } });
}

async function refresh() {
  error.value = "";
  collabError.value = "";

  if (!context.orgId) {
    task.value = null;
    comments.value = [];
    return;
  }

  loading.value = true;
  try {
    const taskRes = await api.getTask(context.orgId, props.taskId);
    task.value = taskRes.task;
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    task.value = null;
    comments.value = [];
    error.value = err instanceof Error ? err.message : String(err);
    return;
  } finally {
    loading.value = false;
  }

  try {
    const commentsRes = await api.listTaskComments(context.orgId, props.taskId);
    comments.value = commentsRes.comments;
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    comments.value = [];
    collabError.value = err instanceof Error ? err.message : String(err);
  }
}

async function submitComment() {
  if (!context.orgId) {
    return;
  }

  collabError.value = "";
  const body = commentDraft.value.trim();
  if (!body) {
    return;
  }

  posting.value = true;
  try {
    await api.createTaskComment(context.orgId, props.taskId, body);
    commentDraft.value = "";
    await refresh();
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    collabError.value = err instanceof Error ? err.message : String(err);
  } finally {
    posting.value = false;
  }
}

watch(() => [context.orgId, props.taskId], () => void refresh(), { immediate: true });
</script>

<template>
  <div class="stack">
    <pf-button variant="link" to="/client/tasks">Back to tasks</pf-button>

    <pf-card>
      <pf-card-body>
        <pf-empty-state v-if="!context.orgId">
          <pf-empty-state-header title="Select an org" heading-level="h2" />
          <pf-empty-state-body>Select an org to continue.</pf-empty-state-body>
        </pf-empty-state>
        <div v-else-if="loading" class="loading-row">
          <pf-spinner size="md" aria-label="Loading task" />
        </div>
        <pf-alert v-else-if="error" inline variant="danger" :title="error" />
        <pf-empty-state v-else-if="!task">
          <pf-empty-state-header title="Not found" heading-level="h2" />
          <pf-empty-state-body>This task does not exist or is not accessible.</pf-empty-state-body>
        </pf-empty-state>

        <div v-else>
          <pf-content>
            <p class="muted">{{ projectName }}</p>
          </pf-content>
          <pf-title h="1" size="2xl">{{ task.title }}</pf-title>
          <div class="labels">
            <VlLabel :color="taskStatusLabelColor(task.status)">{{ workItemStatusLabel(task.status) }}</VlLabel>
            <VlLabel color="blue">Updated {{ formatTimestamp(task.updated_at ?? null) }}</VlLabel>
          </div>

          <pf-content v-if="task.description_html" class="description">
            <!-- description_html is sanitized server-side -->
            <!-- eslint-disable-next-line vue/no-v-html -->
            <div v-html="task.description_html"></div>
          </pf-content>

          <pf-title h="2" size="lg" class="section-title">Schedule</pf-title>
          <div class="muted">{{ task.start_date || "—" }} → {{ task.end_date || "—" }}</div>

          <pf-title h="2" size="lg" class="section-title">Comments</pf-title>
          <pf-alert v-if="collabError" inline variant="danger" :title="collabError" />

          <pf-empty-state v-if="comments.length === 0" variant="small">
            <pf-empty-state-header title="No comments yet" heading-level="h3" />
            <pf-empty-state-body>Post the first comment for this task.</pf-empty-state-body>
          </pf-empty-state>
          <pf-data-list v-else compact aria-label="Task comments">
            <pf-data-list-item v-for="comment in comments" :key="comment.id">
              <pf-data-list-cell>
                <div class="comment-meta">
                  <span class="comment-author">{{ comment.author.display_name || comment.author.id }}</span>
                  <VlLabel color="blue">{{ formatTimestamp(comment.created_at) }}</VlLabel>
                </div>
                <!-- body_html is sanitized server-side -->
                <!-- eslint-disable-next-line vue/no-v-html -->
                <div class="comment-body" v-html="comment.body_html"></div>
              </pf-data-list-cell>
            </pf-data-list-item>
          </pf-data-list>

          <pf-form class="comment-form" @submit.prevent="submitComment">
            <pf-form-group label="New comment" field-id="client-task-comment">
              <pf-textarea
                id="client-task-comment"
                v-model="commentDraft"
                rows="4"
                placeholder="Write a comment (Markdown supported)…"
                :disabled="posting"
              />
            </pf-form-group>
            <pf-button type="submit" variant="primary" :disabled="posting">
              {{ posting ? "Posting…" : "Post comment" }}
            </pf-button>
          </pf-form>
        </div>
      </pf-card-body>
    </pf-card>
  </div>
</template>

<style scoped>
.stack {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.loading-row {
  display: flex;
  justify-content: center;
  padding: 0.75rem 0;
}

.labels {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 0.5rem;
}

.section-title {
  margin-top: 1.25rem;
}

.comment-meta {
  display: flex;
  justify-content: space-between;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.comment-author {
  font-weight: 600;
}

.comment-body :deep(p) {
  margin: 0.25rem 0;
}

.description :deep(p) {
  margin: 0.5rem 0;
}

.comment-form {
  margin-top: 1rem;
}
</style>
