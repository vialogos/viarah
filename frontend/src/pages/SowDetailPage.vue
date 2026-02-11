<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api, ApiError } from "../api";
import type { OrgMembershipWithUser, SoWResponse } from "../api/types";
import VlLabel from "../components/VlLabel.vue";
import { useContextStore } from "../stores/context";
import { useSessionStore } from "../stores/session";
import { formatTimestamp } from "../utils/format";
import { sowPdfStatusLabelColor, sowSignerStatusLabelColor, sowVersionStatusLabelColor } from "../utils/labels";

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
  <div class="stack">
    <pf-button variant="link" to="/sows">Back to SoWs</pf-button>

    <pf-card>
      <pf-card-body>
        <pf-empty-state v-if="!context.orgId">
          <pf-empty-state-header title="Select an org" heading-level="h2" />
          <pf-empty-state-body>Select an org to continue.</pf-empty-state-body>
        </pf-empty-state>
        <div v-else-if="loading" class="loading-row">
          <pf-spinner size="md" aria-label="Loading statement of work" />
        </div>
        <pf-alert v-else-if="error" inline variant="danger" :title="error" />
        <pf-empty-state v-else-if="!sow">
          <pf-empty-state-header title="Not found" heading-level="h2" />
          <pf-empty-state-body>This SoW does not exist or is not accessible.</pf-empty-state-body>
        </pf-empty-state>

        <div v-else>
          <pf-content>
            <p class="muted">{{ projectName }}</p>
          </pf-content>
          <pf-title h="1" size="2xl">SoW v{{ sow.version.version }}</pf-title>

          <div class="labels">
            <VlLabel :color="sowVersionStatusLabelColor(sow.version.status)">{{ sow.version.status }}</VlLabel>
            <VlLabel color="purple">Locked {{ formatTimestamp(sow.version.locked_at) }}</VlLabel>
            <VlLabel color="blue">Updated {{ formatTimestamp(sow.sow.updated_at) }}</VlLabel>
          </div>

          <pf-alert v-if="actionError" inline variant="danger" :title="actionError" />

          <div class="actions">
            <pf-button variant="secondary" :disabled="acting" @click="refresh">Refresh</pf-button>
            <pf-button
              v-if="canManage && sow.version.status === 'draft'"
              variant="primary"
              :disabled="acting"
              @click="sendForSignature"
            >
              Send for signature
            </pf-button>
            <pf-button
              v-if="canManage && sow.version.status === 'signed'"
              variant="primary"
              :disabled="acting"
              @click="requestPdf"
            >
              Request PDF render
            </pf-button>
            <pf-button
              v-if="sow.pdf && sow.pdf.status === 'success'"
              variant="secondary"
              :href="pdfDownloadUrl"
              target="_blank"
              rel="noopener"
            >
              Download PDF
            </pf-button>
          </div>
        </div>
      </pf-card-body>
    </pf-card>

    <pf-card v-if="sow && !loading">
      <pf-card-body>
        <pf-title h="2" size="lg">Signers</pf-title>
        <pf-data-list compact aria-label="SoW signers">
          <pf-data-list-item v-for="signer in sow.signers" :key="signer.id">
            <pf-data-list-cell>
              <div class="signer-name">{{ signerLabel(signer.signer_user_id) }}</div>
              <div class="muted meta labels">
                <VlLabel :color="sowSignerStatusLabelColor(signer.status)">{{ signer.status }}</VlLabel>
                <VlLabel color="blue">Responded {{ formatTimestamp(signer.responded_at) }}</VlLabel>
              </div>
              <div v-if="signer.decision_comment || signer.typed_signature" class="signer-extra">
                <div v-if="signer.decision_comment" class="muted">Comment: {{ signer.decision_comment }}</div>
                <div v-if="signer.typed_signature" class="muted">Signature: {{ signer.typed_signature }}</div>
              </div>
            </pf-data-list-cell>
          </pf-data-list-item>
        </pf-data-list>
      </pf-card-body>
    </pf-card>

    <pf-card v-if="sow && !loading">
      <pf-card-body>
        <pf-title h="2" size="lg">PDF</pf-title>
        <pf-empty-state v-if="!sow.pdf" variant="small">
          <pf-empty-state-header title="Not requested yet" heading-level="h3" />
          <pf-empty-state-body>Request a PDF render once the SoW has been signed.</pf-empty-state-body>
        </pf-empty-state>
        <div v-else>
          <div class="labels">
            <VlLabel :color="sowPdfStatusLabelColor(sow.pdf.status)">Status: {{ sow.pdf.status }}</VlLabel>
            <VlLabel color="blue">Queued {{ formatTimestamp(sow.pdf.created_at) }}</VlLabel>
            <VlLabel color="blue">Started {{ formatTimestamp(sow.pdf.started_at) }}</VlLabel>
            <VlLabel color="blue">Completed {{ formatTimestamp(sow.pdf.completed_at) }}</VlLabel>
          </div>
          <pf-alert
            v-if="sow.pdf.error_message"
            inline
            variant="danger"
            :title="`PDF error: ${sow.pdf.error_message}`"
          />
        </div>
      </pf-card-body>
    </pf-card>

    <pf-card v-if="sow && !loading">
      <pf-card-body>
        <pf-title h="2" size="lg">SoW content</pf-title>
        <!-- body_html is sanitized server-side -->
        <!-- eslint-disable-next-line vue/no-v-html -->
        <div class="content" v-html="sow.version.body_html"></div>
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

.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 0.5rem;
}

.labels {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
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
