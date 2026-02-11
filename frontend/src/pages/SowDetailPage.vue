<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api, ApiError } from "../api";
import type { OrgMembershipWithUser, SoWResponse } from "../api/types";
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
const memberships = ref<OrgMembershipWithUser[]>([]);
const loading = ref(false);
const error = ref("");
const actionError = ref("");
const acting = ref(false);

const currentRole = computed(() => {
  if (!context.orgId) {
    return "";
  }
  return session.memberships.find((m) => m.org.id === context.orgId)?.role ?? "";
});

const canManage = computed(() => currentRole.value === "admin" || currentRole.value === "pm");

const projectName = computed(() => {
  const sowProjectId = sow.value?.sow.project_id || "";
  if (!sowProjectId) {
    return "";
  }
  return context.projects.find((p) => p.id === sowProjectId)?.name ?? "";
});

const membershipByUserId = computed(() => {
  const map: Record<string, OrgMembershipWithUser> = {};
  for (const membership of memberships.value) {
    map[membership.user.id] = membership;
  }
  return map;
});

function signerLabel(userId: string): string {
  const membership = membershipByUserId.value[userId];
  if (!membership) {
    return userId;
  }
  return membership.user.display_name || membership.user.email || userId;
}

async function handleUnauthorized() {
  session.clearLocal("unauthorized");
  await router.push({ path: "/login", query: { redirect: route.fullPath } });
}

async function refresh() {
  error.value = "";
  actionError.value = "";

  if (!context.orgId) {
    sow.value = null;
    memberships.value = [];
    return;
  }

  loading.value = true;
  try {
    const sowRes = await api.getSow(context.orgId, props.sowId);
    sow.value = sowRes;

    if (canManage.value) {
      const membershipsRes = await api.listOrgMemberships(context.orgId, { role: "client" });
      memberships.value = membershipsRes.memberships;
    } else {
      memberships.value = [];
    }
  } catch (err) {
    sow.value = null;
    memberships.value = [];
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

async function sendForSignature() {
  actionError.value = "";
  if (!context.orgId) {
    return;
  }

  acting.value = true;
  try {
    await api.sendSow(context.orgId, props.sowId);
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

async function requestPdf() {
  actionError.value = "";
  if (!context.orgId) {
    return;
  }

  acting.value = true;
  try {
    await api.requestSowPdf(context.orgId, props.sowId);
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
    <RouterLink to="/sows">← Back to SoWs</RouterLink>

    <div class="card detail">
      <div v-if="!context.orgId" class="muted">Select an org to continue.</div>
      <div v-else-if="loading" class="muted">Loading…</div>
      <div v-else-if="error" class="error">{{ error }}</div>
      <div v-else-if="!sow" class="muted">Not found.</div>
      <div v-else>
        <div class="muted">{{ projectName }}</div>
        <h1 class="page-title">SoW v{{ sow.version.version }}</h1>

        <p class="muted labels">
          <VlLabel :color="sowVersionStatusLabelColor(sow.version.status)">{{ sow.version.status }}</VlLabel>
          <VlLabel color="purple">Locked {{ formatTimestamp(sow.version.locked_at) }}</VlLabel>
          <VlLabel color="blue">Updated {{ formatTimestamp(sow.sow.updated_at) }}</VlLabel>
        </p>

        <div v-if="actionError" class="error">{{ actionError }}</div>

        <div class="actions">
          <button type="button" :disabled="acting" @click="refresh">Refresh</button>
          <button
            v-if="canManage && sow.version.status === 'draft'"
            type="button"
            :disabled="acting"
            @click="sendForSignature"
          >
            Send for signature
          </button>
          <button
            v-if="canManage && sow.version.status === 'signed'"
            type="button"
            :disabled="acting"
            @click="requestPdf"
          >
            Request PDF render
          </button>
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

        <div class="card subtle">
          <h3>Signers</h3>
          <ul class="signer-list">
            <li v-for="signer in sow.signers" :key="signer.id" class="signer-row">
              <div class="signer-main">
                <div class="signer-name">{{ signerLabel(signer.signer_user_id) }}</div>
                <div class="muted meta labels">
                  <VlLabel :color="sowSignerStatusLabelColor(signer.status)">{{ signer.status }}</VlLabel>
                  <VlLabel color="blue">Responded {{ formatTimestamp(signer.responded_at) }}</VlLabel>
                </div>
              </div>
              <div v-if="signer.decision_comment || signer.typed_signature" class="signer-extra">
                <div v-if="signer.decision_comment" class="muted">Comment: {{ signer.decision_comment }}</div>
                <div v-if="signer.typed_signature" class="muted">Signature: {{ signer.typed_signature }}</div>
              </div>
            </li>
          </ul>
        </div>

        <div class="card subtle">
          <h3>PDF</h3>
          <div v-if="!sow.pdf" class="muted">Not requested yet.</div>
          <div v-else>
            <div class="muted">
              Status: <strong>{{ sow.pdf.status }}</strong>
            </div>
            <div class="muted">Queued {{ formatTimestamp(sow.pdf.created_at) }}</div>
            <div class="muted">Started {{ formatTimestamp(sow.pdf.started_at) }}</div>
            <div class="muted">Completed {{ formatTimestamp(sow.pdf.completed_at) }}</div>
            <div v-if="sow.pdf.error_message" class="error">PDF error: {{ sow.pdf.error_message }}</div>
          </div>
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

.signer-extra {
  margin-top: 0.5rem;
}

.content :deep(p) {
  margin: 0.25rem 0;
}
</style>
