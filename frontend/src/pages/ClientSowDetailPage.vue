<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api, ApiError } from "../api";
import type { SoWResponse } from "../api/types";
import VlLabel from "../components/VlLabel.vue";
import { useContextStore } from "../stores/context";
import { useRealtimeStore } from "../stores/realtime";
import { useSessionStore } from "../stores/session";
import { formatTimestamp } from "../utils/format";
import { sowSignerStatusLabelColor, sowVersionStatusLabelColor } from "../utils/labels";

const props = defineProps<{ sowId: string }>();

const router = useRouter();
const route = useRoute();
const session = useSessionStore();
const context = useContextStore();
const realtime = useRealtimeStore();

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

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

let refreshTimeoutId: number | null = null;
function scheduleRefresh() {
  if (refreshTimeoutId != null) {
    return;
  }
  refreshTimeoutId = window.setTimeout(() => {
    refreshTimeoutId = null;
    if (loading.value) {
      return;
    }
    void refresh();
  }, 250);
}

const unsubscribeRealtime = realtime.subscribe((event) => {
  if (event.type !== "audit_event.created") {
    return;
  }
  if (!context.orgId) {
    return;
  }
  if (event.org_id && event.org_id !== context.orgId) {
    return;
  }
  if (!isRecord(event.data)) {
    return;
  }

  const auditEventType = typeof event.data.event_type === "string" ? event.data.event_type : "";
  if (!auditEventType.startsWith("sow.")) {
    return;
  }
  const meta = isRecord(event.data.metadata) ? event.data.metadata : {};
  const sowId = String(meta.sow_id ?? "");
  if (!sowId || sowId !== props.sowId) {
    return;
  }
  scheduleRefresh();
});

onBeforeUnmount(() => {
  unsubscribeRealtime();
  if (refreshTimeoutId != null) {
    window.clearTimeout(refreshTimeoutId);
    refreshTimeoutId = null;
  }
});

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
  <div class="stack">
    <pf-button variant="link" to="/client/sows">Back to SoWs</pf-button>

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
          <pf-title h="1" size="2xl">SoW v{{ sow.version.version }}</pf-title>
          <div class="labels">
            <VlLabel :color="sowVersionStatusLabelColor(sow.version.status)">{{ sow.version.status }}</VlLabel>
            <VlLabel color="purple">Locked {{ formatTimestamp(sow.version.locked_at) }}</VlLabel>
            <VlLabel color="blue">Updated {{ formatTimestamp(sow.sow.updated_at) }}</VlLabel>
          </div>

          <div class="actions">
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

          <pf-alert v-if="actionError" inline variant="danger" :title="actionError" />
        </div>
      </pf-card-body>
    </pf-card>

    <pf-card v-if="sow && !loading">
      <pf-card-body>
        <pf-title h="2" size="lg">Signer status</pf-title>
        <pf-data-list compact aria-label="Signer status">
          <pf-data-list-item v-for="signer in sow.signers" :key="signer.id">
            <pf-data-list-cell>
              <div class="signer-name">
                <span v-if="signer.signer_user_id === myUserId">(You)</span>
                <span v-else class="muted">{{ signer.signer_user_id }}</span>
              </div>
              <div class="muted meta labels">
                <VlLabel :color="sowSignerStatusLabelColor(signer.status)">{{ signer.status }}</VlLabel>
                <VlLabel color="blue">Responded {{ formatTimestamp(signer.responded_at) }}</VlLabel>
              </div>
            </pf-data-list-cell>
          </pf-data-list-item>
        </pf-data-list>
      </pf-card-body>
    </pf-card>

    <pf-card v-if="sow && !loading">
      <pf-card-body>
        <pf-title h="2" size="lg">{{ canRespond ? "Approve or reject" : "Decision" }}</pf-title>

        <div v-if="canRespond" class="decision">
          <pf-radio
            id="client-sow-decision-approve"
            name="client-sow-decision"
            label="Approve"
            :checked="decision === 'approve'"
            :disabled="acting"
            @change="decision = 'approve'"
          />
          <pf-radio
            id="client-sow-decision-reject"
            name="client-sow-decision"
            label="Reject"
            :checked="decision === 'reject'"
            :disabled="acting"
            @change="decision = 'reject'"
          />
        </div>

        <pf-form v-if="canRespond" class="decision-form" @submit.prevent="submitDecision">
          <pf-form-group label="Typed signature (required for approve)" field-id="client-sow-typed-signature">
            <pf-text-input
              id="client-sow-typed-signature"
              v-model="typedSignature"
              type="text"
              :disabled="acting || decision === 'reject'"
            />
          </pf-form-group>

          <pf-form-group label="Comment (optional)" field-id="client-sow-comment">
            <pf-textarea id="client-sow-comment" v-model="comment" rows="4" :disabled="acting" />
          </pf-form-group>

          <pf-button type="submit" variant="primary" :disabled="acting">Submit</pf-button>
        </pf-form>

        <pf-content v-else>
          <p v-if="sow.version.status === 'draft'" class="muted">
            This SoW is still a draft. It will be ready to sign once it’s sent for signature.
          </p>
          <p v-else-if="sow.version.status === 'pending_signature'" class="muted">
            Waiting for signer actions.
          </p>
          <p v-else-if="sow.version.status === 'signed'" class="muted">This SoW is signed.</p>
          <p v-else-if="sow.version.status === 'rejected'" class="muted">This SoW was rejected.</p>
        </pf-content>
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

.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 0.5rem;
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

.decision-form {
  margin-top: 1rem;
}

.content :deep(p) {
  margin: 0.25rem 0;
}
</style>
