<script setup lang="ts">
import { ref, watch } from "vue";

import { api } from "../api";
import type { Attachment, Comment, Task } from "../api/types";
import { useContextStore } from "../stores/context";

const props = defineProps<{ taskId: string }>();
const context = useContextStore();

const task = ref<Task | null>(null);
const comments = ref<Comment[]>([]);
const attachments = ref<Attachment[]>([]);
const commentDraft = ref("");
const selectedFile = ref<File | null>(null);
const loading = ref(false);
const error = ref("");
const collabError = ref("");

async function refresh() {
  error.value = "";
  collabError.value = "";

  if (!context.orgId) {
    task.value = null;
    comments.value = [];
    attachments.value = [];
    return;
  }

  loading.value = true;
  try {
    const res = await api.getTask(context.orgId, props.taskId);
    task.value = res.task;
  } catch (err) {
    task.value = null;
    comments.value = [];
    attachments.value = [];
    error.value = err instanceof Error ? err.message : String(err);
    return;
  } finally {
    loading.value = false;
  }

  try {
    const commentsRes = await api.listTaskComments(context.orgId, props.taskId);
    comments.value = commentsRes.comments;
  } catch (err) {
    comments.value = [];
    collabError.value = err instanceof Error ? err.message : String(err);
  }

  try {
    const attachmentsRes = await api.listTaskAttachments(context.orgId, props.taskId);
    attachments.value = attachmentsRes.attachments;
  } catch (err) {
    attachments.value = [];
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

  try {
    await api.createTaskComment(context.orgId, props.taskId, body);
    commentDraft.value = "";
    await refresh();
  } catch (err) {
    collabError.value = err instanceof Error ? err.message : String(err);
  }
}

async function uploadAttachment() {
  if (!context.orgId) {
    return;
  }
  if (!selectedFile.value) {
    return;
  }

  collabError.value = "";
  try {
    await api.uploadTaskAttachment(context.orgId, props.taskId, selectedFile.value);
    selectedFile.value = null;
    await refresh();
  } catch (err) {
    collabError.value = err instanceof Error ? err.message : String(err);
  }
}

function onFileChange(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.item(0);
  selectedFile.value = file ?? null;
}

watch(() => [context.orgId, props.taskId], () => void refresh(), { immediate: true });
</script>

<template>
  <div>
    <RouterLink to="/work">← Back to Work</RouterLink>

    <div class="card detail">
      <div v-if="!context.orgId" class="muted">Select an org to view work.</div>
      <div v-else-if="loading" class="muted">Loading…</div>
      <div v-else-if="error" class="error">{{ error }}</div>
      <div v-else-if="!task" class="muted">Not found.</div>
      <div v-else>
        <h1 class="page-title">{{ task.title }}</h1>
        <p class="muted">{{ task.status }}</p>
        <p v-if="task.description">{{ task.description }}</p>

        <div class="meta">
          <div><span class="muted">Progress</span> {{ Math.round(task.progress * 100) }}%</div>
          <div><span class="muted">Task ID</span> {{ task.id }}</div>
        </div>

        <div class="collaboration">
          <h2 class="section-title">Collaboration</h2>
          <div v-if="collabError" class="error">{{ collabError }}</div>

          <div class="collaboration-grid">
            <div class="card comments">
              <h3>Comments</h3>

              <div v-if="comments.length === 0" class="muted">No comments yet.</div>
              <div v-else class="comment-list">
                <div v-for="comment in comments" :key="comment.id" class="comment">
                  <div class="comment-meta">
                    <span class="comment-author">{{
                      comment.author.display_name || comment.author.id
                    }}</span>
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
                />
                <button class="primary" type="button" @click="submitComment">Post comment</button>
              </div>
            </div>

            <div class="card attachments">
              <h3>Attachments</h3>

              <div v-if="attachments.length === 0" class="muted">No attachments yet.</div>
              <div v-else class="attachment-list">
                <div
                  v-for="attachment in attachments"
                  :key="attachment.id"
                  class="attachment-row"
                >
                  <div class="attachment-name">{{ attachment.filename }}</div>
                  <div class="attachment-meta muted">
                    {{ attachment.size_bytes }} bytes • {{ attachment.content_type }}
                  </div>
                  <a class="attachment-link" :href="attachment.download_url">Download</a>
                </div>
              </div>

              <div class="attachment-form">
                <input
                  type="file"
                  @change="onFileChange"
                />
                <button type="button" class="primary" @click="uploadAttachment">Upload</button>
              </div>
            </div>
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

.meta {
  margin-top: 1rem;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.5rem;
}

.collaboration {
  margin-top: 1.5rem;
}

.section-title {
  margin: 0 0 0.75rem;
}

.collaboration-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
  margin-top: 0.75rem;
}

.comment-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  margin-top: 0.75rem;
}

.comment-meta {
  display: flex;
  justify-content: space-between;
  gap: 0.75rem;
}

.comment-author {
  font-weight: 600;
}

.comment-body :deep(p) {
  margin: 0.25rem 0 0;
}

.comment-form {
  margin-top: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.attachment-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  margin-top: 0.75rem;
}

.attachment-row {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 0.25rem 0.75rem;
  align-items: center;
}

.attachment-meta {
  grid-column: 1 / -1;
}

.attachment-link {
  justify-self: end;
}

.attachment-form {
  margin-top: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
</style>
