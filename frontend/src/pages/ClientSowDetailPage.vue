<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api, ApiError } from "../api";
import type { SoWResponse } from "../api/types";
import VlLabel from "../components/VlLabel.vue";
import { useContextStore } from "../stores/context";
import { useSessionStore } from "../stores/session";
import { formatTimestamp } from "../utils/format";
import { sowSignerStatusLabelColor, sowVersionStatusLabelColor } from "../utils/labels";

const props = defineProps<{ sowId: string }>();

const router = useRouter();
const route = useRoute();
const session = useSessionStore();
const context = useContextStore();

const sow = ref<SoWResponse | null>(null);
const loading = ref(false);
const error = ref("");
const actionError = ref("");
const acting = ref(false);

const decision = ref<"approve" | "reject">("approve");
const typedSignature = ref("");
const comment = ref("");

const myUserId = computed(() => session.user?.id ?? "");
const mySigner = computed(() => {
  if (!myUserId.value) {
    return null;
  }
  return sow.value?.signers.find((s) => s.signer_user_id === myUserId.value) ?? null;
});

const canRespond = computed(() => {
  return Boolean(sow.value && sow.value.version.status === "pending_signature" && mySigner.value?.status === "pending");
});

async function handleUnauthorized() {
  session.clearLocal("unauthorized");
  await router.push({ path: "/login", query: { redirect: route.fullPath } });
}

async function refresh() {
  error.value = "";
  actionError.value = "";

  if (!context.orgId) {
    sow.value = null;
    return;
  }

  loading.value = true;
  try {
    sow.value = await api.getSow(context.orgId, props.sowId);
  } catch (err) {
    sow.value = null;
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

watch(() => [context.orgId, props.sowId], () => void refresh(), { immediate: true });

async function submitDecision() {
  actionError.value = "";
  if (!context.orgId) {
    return;
  }
  if (!canRespond.value) {
    actionError.value = "This SoW is not awaiting your signature.";
    return;
  }

  if (decision.value === "approve" && !typedSignature.value.trim()) {
    actionError.value = "Typed signature is required to approve.";
    return;
  }

  acting.value = true;
  try {
    if (decision.value === "approve") {
      await api.respondSow(context.orgId, props.sowId, {
        decision: "approve",
        typed_signature: typedSignature.value.trim(),
        comment: comment.value.trim() || undefined,
      });
    } else {
      await api.respondSow(context.orgId, props.sowId, {
        decision: "reject",
        comment: comment.value.trim() || undefined,
      });
    }
    await refresh();
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    actionError.value = err instanceof Error ? err.message : String(err);
  } finally {
    acting.value = false;
  }
}

const pdfDownloadUrl = computed(() => {
  if (!context.orgId) {
    return "";
  }
  return `/api/orgs/${context.orgId}/sows/${props.sowId}/pdf`;
});
</script>

<template>
  <div>
    <RouterLink to="/client/sows">← Back to SoWs</RouterLink>

    <div class="card detail">
      <div v-if="!context.orgId" class="muted">Select an org to continue.</div>
      <div v-else-if="loading" class="muted">Loading…</div>
      <div v-else-if="error" class="error">{{ error }}</div>
      <div v-else-if="!sow" class="muted">Not found.</div>
      <div v-else>
        <h1 class="page-title">SoW v{{ sow.version.version }}</h1>
        <p class="muted labels">
          <VlLabel :color="sowVersionStatusLabelColor(sow.version.status)">{{ sow.version.status }}</VlLabel>
          <VlLabel color="purple">Locked {{ formatTimestamp(sow.version.locked_at) }}</VlLabel>
          <VlLabel color="blue">Updated {{ formatTimestamp(sow.sow.updated_at) }}</VlLabel>
        </p>

        <div class="actions">
          <button type="button" :disabled="acting" @click="refresh">Refresh</button>
          <a
            v-if="sow.pdf && sow.pdf.status === 'success'"
            class="button-link"
            :href="pdfDownloadUrl"
            target="_blank"
            rel="noopener"
          >
            Download PDF
          </a>
        </div>

        <div v-if="actionError" class="error">{{ actionError }}</div>

        <div class="card subtle">
          <h3>Signer status</h3>
          <ul class="signer-list">
            <li v-for="signer in sow.signers" :key="signer.id" class="signer-row">
              <div>
                <div class="signer-name">
                  <span v-if="signer.signer_user_id === myUserId">(You)</span>
                  <span v-else class="muted">{{ signer.signer_user_id }}</span>
                </div>
                <div class="muted meta labels">
                  <VlLabel :color="sowSignerStatusLabelColor(signer.status)">{{ signer.status }}</VlLabel>
                  <VlLabel color="blue">Responded {{ formatTimestamp(signer.responded_at) }}</VlLabel>
                </div>
              </div>
            </li>
          </ul>
        </div>

        <div v-if="canRespond" class="card subtle">
          <h3>Approve or reject</h3>

          <div class="decision">
            <label class="radio">
              <input v-model="decision" type="radio" value="approve" :disabled="acting" />
              Approve
            </label>
            <label class="radio">
              <input v-model="decision" type="radio" value="reject" :disabled="acting" />
              Reject
            </label>
          </div>

          <label class="field">
            <span class="label">Typed signature (required for approve)</span>
            <input v-model="typedSignature" type="text" :disabled="acting || decision === 'reject'" />
          </label>

          <label class="field">
            <span class="label">Comment (optional)</span>
            <textarea v-model="comment" rows="4" :disabled="acting" />
          </label>

          <button type="button" :disabled="acting" @click="submitDecision">Submit</button>
        </div>

        <div v-else class="card subtle">
          <h3>Decision</h3>
          <div v-if="sow.version.status === 'draft'" class="muted">
            This SoW is still a draft. It will be ready to sign once it’s sent for signature.
          </div>
          <div v-else-if="sow.version.status === 'pending_signature'" class="muted">
            Waiting for signer actions.
          </div>
          <div v-else-if="sow.version.status === 'signed'" class="muted">This SoW is signed.</div>
          <div v-else-if="sow.version.status === 'rejected'" class="muted">This SoW was rejected.</div>
        </div>

        <div class="card subtle">
          <h3>SoW content</h3>
          <!-- body_html is sanitized server-side -->
          <!-- eslint-disable-next-line vue/no-v-html -->
          <div class="content" v-html="sow.version.body_html"></div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.detail {
  margin-top: 1rem;
}

.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 0.75rem;
}

.button-link {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  border: 1px solid var(--border);
  padding: 0.5rem 0.85rem;
  background: var(--panel);
  color: var(--text);
  text-decoration: none;
}

.button-link:hover {
  border-color: #cbd5e1;
}

.labels {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.card.subtle {
  margin-top: 1rem;
  border-color: #e5e7eb;
  background: #fafafa;
}

.signer-list {
  list-style: none;
  padding: 0;
  margin: 0.75rem 0 0 0;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.signer-row {
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 0.75rem;
  background: #fbfbfd;
}

.signer-name {
  font-weight: 600;
}

.meta {
  font-size: 0.9rem;
}

.decision {
  display: flex;
  gap: 1.5rem;
  margin-top: 0.5rem;
}

.radio {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  margin-top: 0.75rem;
}

.label {
  font-size: 0.85rem;
  color: var(--muted);
}

textarea {
  border-radius: 10px;
  border: 1px solid var(--border);
  padding: 0.75rem;
  resize: vertical;
}

.content :deep(p) {
  margin: 0.25rem 0;
}
</style>
