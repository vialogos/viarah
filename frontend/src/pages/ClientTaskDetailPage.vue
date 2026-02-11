<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api, ApiError } from "../api";
import type { Comment, Task } from "../api/types";
import { useContextStore } from "../stores/context";
import { useSessionStore } from "../stores/session";

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
  <div>
    <RouterLink to="/client/tasks">← Back to tasks</RouterLink>

    <div class="card detail">
      <div v-if="!context.orgId" class="muted">Select an org to continue.</div>
      <div v-else-if="loading" class="muted">Loading…</div>
      <div v-else-if="error" class="error">{{ error }}</div>
      <div v-else-if="!task" class="muted">Not found.</div>
      <div v-else>
        <div class="muted">{{ projectName }}</div>
        <h1 class="page-title">{{ task.title }}</h1>
        <p class="muted">
          <span class="chip">{{ task.status }}</span>
          <span class="chip">Updated {{ task.updated_at ? new Date(task.updated_at).toLocaleString() : "—" }}</span>
        </p>

        <div class="card subtle">
          <h3>Schedule</h3>
          <div class="muted">{{ task.start_date || "—" }} → {{ task.end_date || "—" }}</div>
        </div>

        <div class="collaboration">
          <h2 class="section-title">Comments</h2>
          <div v-if="collabError" class="error">{{ collabError }}</div>

          <div v-if="comments.length === 0" class="muted">No comments yet.</div>
          <div v-else class="comment-list">
            <div v-for="comment in comments" :key="comment.id" class="comment">
              <div class="comment-meta">
                <span class="comment-author">{{ comment.author.display_name || comment.author.id }}</span>
                <span class="muted">{{ new Date(comment.created_at).toLocaleString() }}</span>
              </div>
              <!-- body_html is sanitized server-side -->
              <!-- eslint-disable-next-line vue/no-v-html -->
              <div class="comment-body" v-html="comment.body_html"></div>
            </div>
          </div>

          <div class="comment-form">
            <textarea
              v-model="commentDraft"
              rows="4"
              placeholder="Write a comment (Markdown supported)…"
              :disabled="posting"
            />
            <button class="primary" type="button" :disabled="posting" @click="submitComment">Post comment</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.detail {
  margin-top: 1rem;
}

.chip {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  font-size: 0.85rem;
  padding: 0.1rem 0.5rem;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: #f8fafc;
  margin-right: 0.5rem;
  margin-top: 0.25rem;
}

.card.subtle {
  margin-top: 1rem;
  border-color: #e5e7eb;
  background: #fafafa;
}

.section-title {
  margin-top: 1.5rem;
  margin-bottom: 0.5rem;
  font-size: 1.1rem;
}

.comment-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  margin-top: 0.75rem;
}

.comment {
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 0.75rem;
  background: #fafafa;
}

.comment-meta {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 0.25rem;
}

.comment-author {
  font-weight: 600;
}

.comment-body :deep(p) {
  margin: 0.25rem 0;
}

.comment-form {
  margin-top: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

textarea {
  border-radius: 10px;
  border: 1px solid var(--border);
  padding: 0.75rem;
  resize: vertical;
}
</style>

