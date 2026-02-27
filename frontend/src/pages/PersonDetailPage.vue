<script setup lang="ts">
	import { computed, onBeforeUnmount, ref, watch } from "vue";
	import { useRoute, useRouter } from "vue-router";
	import xss from "xss";

		import { api, ApiError } from "../api";
		import type { Person, PersonMessage, PersonMessageThread, PersonProjectMembership } from "../api/types";
		import ActivityStream from "../components/ActivityStream.vue";
		import TeamPersonModal from "../components/team/TeamPersonModal.vue";
		import VlInitialsAvatar from "../components/VlInitialsAvatar.vue";
		import VlLabel from "../components/VlLabel.vue";
		import VlMarkdownEditor from "../components/VlMarkdownEditor.vue";
	import { useContextStore } from "../stores/context";
	import { useRealtimeStore } from "../stores/realtime";
	import { useSessionStore } from "../stores/session";
	import { formatTimestamp } from "../utils/format";
	import type { VlLabelColor } from "../utils/labels";

const props = defineProps<{ personId: string }>();

const router = useRouter();
	const route = useRoute();
		const session = useSessionStore();
		const context = useContextStore();
		const realtime = useRealtimeStore();

		const currentRole = computed(() => {
		  return session.effectiveOrgRole(context.orgId);
		});
	
		const canManage = computed(() => currentRole.value === "admin" || currentRole.value === "pm");
	
	const loading = ref(false);
	const error = ref("");

	const person = ref<Person | null>(null);
	const memberships = ref<PersonProjectMembership[]>([]);

		const personModalOpen = ref(false);
		const personModalInitialSection = ref<"profile" | "invite">("profile");
	
			const inviteMaterial = ref<
			  null | { token: string; invite_url: string; full_invite_url: string; email_sent?: boolean }
			>(null);
		const inviteClipboardStatus = ref("");
	
	const threads = ref<PersonMessageThread[]>([]);
	const selectedThreadId = ref<string | null>(null);
	const messages = ref<PersonMessage[]>([]);
	const messagesLoading = ref(false);
const messageError = ref("");

const newThreadTitle = ref("");
const creatingThread = ref(false);
const newMessageBody = ref("");
	const sendingMessage = ref(false);

	const selectedAvatarFile = ref<File | null>(null);
	const avatarUploadKey = ref(0);
	const avatarUploading = ref(false);
	const avatarError = ref("");

	const clipboardStatus = ref("");
	let clipboardClearTimeoutId: number | null = null;

	const selectedThread = computed(() => threads.value.find((t) => t.id === selectedThreadId.value) ?? null);

	function shortId(value: string): string {
	  if (!value) {
	    return "";
  }
  if (value.length <= 12) {
    return value;
  }
  return `${value.slice(0, 6)}…${value.slice(-4)}`;
}

function messageAuthorLabel(message: PersonMessage): string {
  const user = session.user;
  if (user && message.author_user_id === user.id) {
    return user.display_name || user.email;
  }
  return shortId(message.author_user_id);
}

function safeMessageHtml(html: unknown): string {
  return xss(String(html ?? ""));
}

		function personDisplay(p: Person | null): string {
		  if (!p) {
		    return "Person";
		  }
	  const label = (p.preferred_name || p.full_name || p.email || "").trim();
	  return label || "Unnamed";
	}

	function roleLabelColor(role: string): VlLabelColor {
	  if (role === "admin") {
	    return "red";
	  }
	  if (role === "pm") {
	    return "purple";
	  }
	  if (role === "client") {
	    return "teal";
	  }
	  return "blue";
	}

	function personStatusLabelColor(status: string): VlLabelColor {
	  if (status === "active") {
	    return "green";
	  }
	  if (status === "invited") {
	    return "orange";
	  }
	  return "grey";
	}

		async function copyToClipboard(label: string, value: string) {
		  clipboardStatus.value = "";
		  const trimmed = String(value || "").trim();
		  if (!trimmed) {
		    clipboardStatus.value = `No ${label} to copy.`;
	    return;
	  }
	  if (typeof navigator === "undefined" || !navigator.clipboard?.writeText) {
	    clipboardStatus.value = "Clipboard not available.";
	    return;
	  }
	  try {
	    await navigator.clipboard.writeText(trimmed);
	    clipboardStatus.value = `Copied ${label}.`;
	  } catch {
	    clipboardStatus.value = "Copy failed.";
	  }

	  if (clipboardClearTimeoutId != null) {
	    window.clearTimeout(clipboardClearTimeoutId);
	  }
	  clipboardClearTimeoutId = window.setTimeout(() => {
	    clipboardClearTimeoutId = null;
	    clipboardStatus.value = "";
		  }, 2000);
		}

		function absoluteInviteUrl(inviteUrl: string): string {
		  try {
		    if (typeof window === "undefined") {
		      return inviteUrl;
		    }
		    return new URL(inviteUrl, window.location.origin).toString();
		  } catch {
		    return inviteUrl;
		  }
		}
	
		function dismissInviteMaterial() {
		  inviteMaterial.value = null;
		  inviteClipboardStatus.value = "";
		}
	
			function showInviteMaterial(material: {
			  token: string;
			  invite_url: string;
			  full_invite_url?: string;
			  email_sent?: boolean;
			}) {
			  inviteMaterial.value = {
			    token: material.token,
			    invite_url: material.invite_url,
			    full_invite_url: material.full_invite_url || absoluteInviteUrl(material.invite_url),
			    email_sent: material.email_sent,
			  };
			  inviteClipboardStatus.value = "";
			}
	
		async function copyInviteText(value: string) {
		  inviteClipboardStatus.value = "";
		  if (!value) {
		    return;
		  }
	
		  try {
		    if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
		      await navigator.clipboard.writeText(value);
		      inviteClipboardStatus.value = "Copied.";
		      return;
		    }
		    throw new Error("Clipboard API unavailable");
		  } catch {
		    inviteClipboardStatus.value = "Copy failed; select and copy manually.";
		  }
		}
	
		function openEditPerson() {
		  if (!person.value) {
		    return;
		  }
		  personModalInitialSection.value = "profile";
		  personModalOpen.value = true;
		}
	
		function openInvitePerson() {
		  if (!person.value) {
		    return;
		  }
		  personModalInitialSection.value = "invite";
		  personModalOpen.value = true;
		}
	
		function onPersonSaved(next: Person) {
		  person.value = next;
		  void refresh();
		}

		function isRecord(value: unknown): value is Record<string, unknown> {
		  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
		}

	async function handleUnauthorized() {
	  session.clearLocal("unauthorized");
	  await router.push({ path: "/login", query: { redirect: route.fullPath } });
	}

async function refresh() {
  error.value = "";
  avatarError.value = "";

  if (!context.orgId) {
    person.value = null;
    memberships.value = [];
    threads.value = [];
    selectedThreadId.value = null;
    messages.value = [];
    return;
  }

  loading.value = true;
  try {
    const [personRes, membershipsRes, threadsRes] = await Promise.all([
      api.getOrgPerson(context.orgId, props.personId),
      api.listPersonProjectMemberships(context.orgId, props.personId),
      api.listPersonMessageThreads(context.orgId, props.personId),
    ]);
    person.value = personRes.person;
    memberships.value = membershipsRes.memberships;
    threads.value = threadsRes.threads;
    if (!selectedThreadId.value) {
      const first = threadsRes.threads[0];
      if (first) {
        selectedThreadId.value = first.id;
      }
    }
  } catch (err) {
    person.value = null;
    memberships.value = [];
    threads.value = [];
    selectedThreadId.value = null;
    messages.value = [];

    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

function onSelectedAvatarFileChange(payload: unknown) {
  if (payload instanceof File) {
    selectedAvatarFile.value = payload;
    return;
  }
  selectedAvatarFile.value = null;
}

async function uploadAvatar() {
  avatarError.value = "";
  if (!context.orgId) {
    avatarError.value = "Select an org first.";
    return;
  }
  if (!selectedAvatarFile.value) {
    avatarError.value = "Choose a file first.";
    return;
  }
  avatarUploading.value = true;
  try {
    const res = await api.uploadPersonAvatar(context.orgId, props.personId, selectedAvatarFile.value);
    person.value = res.person;
    selectedAvatarFile.value = null;
    avatarUploadKey.value += 1;
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    avatarError.value = err instanceof Error ? err.message : String(err);
  } finally {
    avatarUploading.value = false;
  }
}

async function clearAvatar() {
  avatarError.value = "";
  if (!context.orgId) {
    avatarError.value = "Select an org first.";
    return;
  }
  avatarUploading.value = true;
  try {
    const res = await api.clearPersonAvatar(context.orgId, props.personId);
    person.value = res.person;
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    avatarError.value = err instanceof Error ? err.message : String(err);
  } finally {
    avatarUploading.value = false;
  }
}

async function refreshMessages() {
  messageError.value = "";
  messages.value = [];

  if (!context.orgId) {
    return;
  }
  if (!selectedThreadId.value) {
    return;
  }

  messagesLoading.value = true;
  try {
    const res = await api.listPersonThreadMessages(context.orgId, props.personId, selectedThreadId.value);
    messages.value = res.messages;
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    messageError.value = err instanceof Error ? err.message : String(err);
  } finally {
    messagesLoading.value = false;
  }
}

async function createThread() {
  messageError.value = "";
  if (!context.orgId) {
    messageError.value = "Select an org first.";
    return;
  }
  const title = newThreadTitle.value.trim();
  if (!title) {
    messageError.value = "Thread title is required.";
    return;
  }

  creatingThread.value = true;
  try {
    const res = await api.createPersonMessageThread(context.orgId, props.personId, { title });
    threads.value = [res.thread, ...threads.value];
    selectedThreadId.value = res.thread.id;
    newThreadTitle.value = "";
    await refreshMessages();
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    messageError.value = err instanceof Error ? err.message : String(err);
  } finally {
    creatingThread.value = false;
  }
}

async function sendMessage() {
  messageError.value = "";
  if (!context.orgId) {
    messageError.value = "Select an org first.";
    return;
  }
  if (!selectedThreadId.value) {
    messageError.value = "Select a thread first.";
    return;
  }
  const body = newMessageBody.value.trim();
  if (!body) {
    messageError.value = "Message is required.";
    return;
  }

	  sendingMessage.value = true;
	  try {
	    const res = await api.createPersonThreadMessage(context.orgId, props.personId, selectedThreadId.value, {
	      body_markdown: body,
	      project_id: context.projectId || undefined,
	    });
	    messages.value = [...messages.value, res.message];
	    newMessageBody.value = "";
	  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    messageError.value = err instanceof Error ? err.message : String(err);
  } finally {
    sendingMessage.value = false;
  }
}

		watch(() => [context.orgId, props.personId], refresh, { immediate: true });
		watch(() => selectedThreadId.value, () => void refreshMessages(), { immediate: true });

		let refreshQueued = false;
		let refreshMessagesQueued = false;
	
		function scheduleRefresh() {
		  if (refreshQueued) {
		    return;
		  }
		  refreshQueued = true;
		  Promise.resolve().then(() => {
		    refreshQueued = false;
		    if (loading.value) {
		      return;
		    }
		    void refresh();
		  });
		}

		function scheduleRefreshMessages() {
		  if (refreshMessagesQueued) {
		    return;
		  }
		  refreshMessagesQueued = true;
		  Promise.resolve().then(() => {
		    refreshMessagesQueued = false;
		    if (messagesLoading.value) {
		      return;
		    }
		    void refreshMessages();
		  });
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
	  const meta = isRecord(event.data.metadata) ? event.data.metadata : {};
	  const personId = typeof meta.person_id === "string" ? meta.person_id : "";
	  if (!personId || personId !== props.personId) {
	    return;
	  }

	  scheduleRefresh();

	  if (!auditEventType.startsWith("person_message.")) {
	    return;
	  }
	  const threadId = typeof meta.thread_id === "string" ? meta.thread_id : "";
	  if (!threadId || threadId !== selectedThreadId.value) {
	    return;
	  }
	  scheduleRefreshMessages();
	});

		onBeforeUnmount(() => {
		  unsubscribeRealtime();
		  if (clipboardClearTimeoutId != null) {
		    window.clearTimeout(clipboardClearTimeoutId);
		    clipboardClearTimeoutId = null;
		  }
	});
	</script>

<template>
  <div class="stack">
    <pf-button variant="link" @click="router.back()">Back</pf-button>

    <pf-card>
      <pf-card-title>
        <div class="header">
          <div class="header-left">
            <VlInitialsAvatar :label="personDisplay(person)" :src="person?.avatar_url" size="lg" bordered />
            <div class="header-text">
              <pf-title h="1" size="2xl">{{ personDisplay(person) }}</pf-title>
              <div v-if="person?.email" class="muted">{{ person.email }}</div>
              <div v-if="person" class="muted small">Updated {{ formatTimestamp(person.updated_at) }}</div>
            </div>
          </div>
          <div v-if="person" class="header-right">
            <div class="header-meta">
              <VlLabel v-if="person.membership_role" :color="roleLabelColor(person.membership_role)" variant="outline">
                {{ person.membership_role.toUpperCase() }}
              </VlLabel>
              <VlLabel v-if="person.status" :color="personStatusLabelColor(person.status)" variant="outline">
                {{ person.status.toUpperCase() }}
              </VlLabel>
            </div>

            <div class="header-actions">
              <pf-button v-if="canManage" variant="primary" small type="button" @click="openEditPerson">
                Edit person
              </pf-button>
              <pf-button
                v-if="canManage && (person.status === 'candidate' || person.status === 'invited')"
                variant="secondary"
                small
                type="button"
                @click="openInvitePerson"
              >
                {{ person.active_invite ? "Manage invite" : "Invite" }}
              </pf-button>
              <pf-button
                v-if="person.email"
                variant="secondary"
                small
                :href="`mailto:${person.email}`"
                target="_blank"
                rel="noopener noreferrer"
              >
                Email
              </pf-button>
              <pf-button
                v-if="person.email"
                variant="secondary"
                small
                type="button"
                @click="copyToClipboard('email', person.email)"
              >
                Copy email
              </pf-button>
              <pf-button
                v-if="person.linkedin_url"
                variant="secondary"
                small
                :href="person.linkedin_url"
                target="_blank"
                rel="noopener noreferrer"
              >
                LinkedIn
              </pf-button>
              <pf-button
                v-if="person.gitlab_username"
                variant="secondary"
                small
                :href="`https://gitlab.com/${person.gitlab_username}`"
                target="_blank"
                rel="noopener noreferrer"
              >
                GitLab
              </pf-button>
            </div>

            <div v-if="clipboardStatus" class="muted small">{{ clipboardStatus }}</div>
          </div>
        </div>
      </pf-card-title>
      <pf-card-body>
        <pf-alert v-if="error" inline variant="danger" :title="error" />
        <pf-empty-state v-else-if="!context.orgId" variant="small">
          <pf-empty-state-header title="Select an org" heading-level="h2" />
          <pf-empty-state-body>Select an org to view a person.</pf-empty-state-body>
        </pf-empty-state>
        <div v-else-if="loading" class="loading-row">
          <pf-spinner size="md" aria-label="Loading person" />
        </div>
        <div v-else-if="person" class="details-stack">
          <pf-card class="avatar-card">
            <pf-card-title>
              <pf-title h="2" size="lg">Avatar</pf-title>
            </pf-card-title>
            <pf-card-body>
              <pf-alert v-if="avatarError" inline variant="danger" :title="avatarError" />

              <div class="avatar-row">
                <VlInitialsAvatar :label="personDisplay(person)" :src="person.avatar_url" size="xl" bordered />
                <div class="avatar-actions">
                  <pf-file-upload
                    :key="avatarUploadKey"
                    browse-button-text="Choose image"
                    hide-default-preview
                    :disabled="avatarUploading"
                    @file-input-change="onSelectedAvatarFileChange"
                  >
                    <div class="muted small">
                      {{
                        selectedAvatarFile
                          ? `${selectedAvatarFile.name} (${selectedAvatarFile.size} bytes)`
                          : "No file selected."
                      }}
                    </div>
                  </pf-file-upload>

                  <div class="avatar-buttons">
                    <pf-button type="button" variant="primary" :disabled="!selectedAvatarFile || avatarUploading" @click="uploadAvatar">
                      {{ avatarUploading ? "Uploading…" : "Upload" }}
                    </pf-button>
                    <pf-button type="button" variant="secondary" :disabled="avatarUploading || !person.avatar_url" @click="clearAvatar">
                      Clear
                    </pf-button>
                  </div>
                </div>
              </div>
            </pf-card-body>
          </pf-card>

          <div class="details-grid">
            <div class="detail">
              <div class="label">Title</div>
              <div class="value">{{ person.title || "—" }}</div>
            </div>
            <div class="detail">
              <div class="label">Timezone</div>
              <div class="value">{{ person.timezone || "—" }}</div>
            </div>
            <div class="detail">
              <div class="label">Location</div>
              <div class="value">{{ person.location || "—" }}</div>
            </div>
            <div class="detail">
              <div class="label">Phone</div>
              <div class="value">{{ person.phone || "—" }}</div>
            </div>
            <div class="detail">
              <div class="label">Slack</div>
              <div class="value">{{ person.slack_handle || "—" }}</div>
            </div>
            <div class="detail">
              <div class="label">LinkedIn</div>
              <div class="value">
                <a v-if="person.linkedin_url" :href="person.linkedin_url" target="_blank" rel="noopener noreferrer">
                  {{ person.linkedin_url }}
                </a>
                <span v-else>—</span>
              </div>
            </div>
            <div class="detail full">
              <div class="label">Skills</div>
              <div class="value">
                <pf-label-group v-if="person.skills?.length" :num-labels="8">
                  <VlLabel v-for="skill in person.skills" :key="skill" color="blue" variant="outline">{{ skill }}</VlLabel>
                </pf-label-group>
                <span v-else class="muted">—</span>
              </div>
            </div>
            <div class="detail full">
              <div class="label">Bio</div>
              <div class="value">{{ person.bio || "—" }}</div>
            </div>
            <div class="detail full">
              <div class="label">Notes</div>
              <div class="value">{{ person.notes || "—" }}</div>
            </div>
          </div>
        </div>
      </pf-card-body>
    </pf-card>

    <pf-card>
      <pf-card-title>
        <div class="section-title">
          <pf-title h="2" size="xl">Projects</pf-title>
          <VlLabel v-if="memberships.length" color="blue" variant="outline">{{ memberships.length }}</VlLabel>
        </div>
      </pf-card-title>
      <pf-card-body>
        <pf-empty-state v-if="!memberships.length" variant="small">
          <pf-empty-state-header title="No project memberships" heading-level="h3" />
          <pf-empty-state-body>This person isn’t added to any projects.</pf-empty-state-body>
        </pf-empty-state>
        <pf-table v-else aria-label="Person project memberships">
          <pf-thead>
            <pf-tr>
              <pf-th>Project</pf-th>
              <pf-th>Added</pf-th>
            </pf-tr>
          </pf-thead>
          <pf-tbody>
            <pf-tr v-for="membership in memberships" :key="membership.id">
              <pf-td data-label="Project">{{ membership.project.name }}</pf-td>
              <pf-td data-label="Added">{{ formatTimestamp(membership.created_at) }}</pf-td>
            </pf-tr>
          </pf-tbody>
        </pf-table>
      </pf-card-body>
    </pf-card>

    <ActivityStream :org-id="context.orgId" :person-id="props.personId" title="Activity" />

    <pf-card>
      <pf-card-title>
        <div class="section-title">
          <pf-title h="2" size="xl">Messages</pf-title>
          <VlLabel v-if="threads.length" color="blue" variant="outline">{{ threads.length }}</VlLabel>
        </div>
      </pf-card-title>
      <pf-card-body>
        <pf-alert v-if="messageError" inline variant="danger" :title="messageError" />

        <pf-empty-state v-if="!context.orgId" variant="small">
          <pf-empty-state-header title="Select an org" heading-level="h3" />
          <pf-empty-state-body>Select an org to view messages.</pf-empty-state-body>
        </pf-empty-state>

        <div v-else class="messages-grid">
          <div class="threads">
            <pf-form class="thread-create" @submit.prevent="createThread">
              <pf-form-group label="New thread" field-id="thread-title">
                <pf-text-input
                  id="thread-title"
                  v-model="newThreadTitle"
                  type="text"
                  placeholder="Thread title…"
                  :disabled="creatingThread"
                />
              </pf-form-group>
              <pf-button
                variant="secondary"
                type="button"
                :disabled="creatingThread || !newThreadTitle.trim()"
                @click="createThread"
              >
                {{ creatingThread ? "Creating…" : "Create" }}
              </pf-button>
            </pf-form>

            <pf-empty-state v-if="!threads.length" variant="small">
              <pf-empty-state-header title="No threads yet" heading-level="h3" />
              <pf-empty-state-body>Create a thread to start messaging.</pf-empty-state-body>
            </pf-empty-state>

            <pf-data-list v-else aria-label="Message threads">
              <pf-data-list-item
                v-for="thread in threads"
                :key="thread.id"
                :aria-label="thread.title"
                class="thread-item"
                :class="{ selected: thread.id === selectedThreadId }"
                @click="selectedThreadId = thread.id"
              >
                <pf-data-list-item-row>
                  <pf-data-list-item-cells>
                    <pf-data-list-cell>
                      <div class="thread-row">
                        <div class="thread-title">{{ thread.title }}</div>
                        <div class="muted small">
                          {{ thread.message_count }} msg · updated {{ formatTimestamp(thread.updated_at) }}
                        </div>
                      </div>
                    </pf-data-list-cell>
                  </pf-data-list-item-cells>
                </pf-data-list-item-row>
              </pf-data-list-item>
            </pf-data-list>
          </div>

          <div class="thread-detail">
            <pf-empty-state v-if="!selectedThread" variant="small">
              <pf-empty-state-header title="Select a thread" heading-level="h3" />
              <pf-empty-state-body>Pick a thread to read and send messages.</pf-empty-state-body>
            </pf-empty-state>

            <div v-else class="thread-stack">
              <div class="thread-header">
                <pf-title h="3" size="lg">{{ selectedThread.title }}</pf-title>
                <div class="muted small">Updated {{ formatTimestamp(selectedThread.updated_at) }}</div>
              </div>

              <div v-if="messagesLoading" class="loading-row">
                <pf-spinner size="md" aria-label="Loading messages" />
              </div>

              <pf-empty-state v-else-if="!messages.length" variant="small">
                <pf-empty-state-header title="No messages yet" heading-level="h4" />
                <pf-empty-state-body>Send the first message below.</pf-empty-state-body>
              </pf-empty-state>

              <div v-else class="message-list" aria-label="Messages">
                <div v-for="message in messages" :key="message.id" class="message">
                  <div class="message-meta muted small">
                    {{ formatTimestamp(message.created_at) }} · {{ messageAuthorLabel(message) }}
                  </div>
                  <!-- eslint-disable-next-line vue/no-v-html -->
                  <div class="message-body" v-html="safeMessageHtml(message.body_html)"></div>
                </div>
              </div>

              <pf-divider />

              <pf-form class="composer" @submit.prevent="sendMessage">
                <pf-form-group label="New message" field-id="message-body">
                  <VlMarkdownEditor id="message-body" v-model="newMessageBody" placeholder="Write a message…" />
                </pf-form-group>
                <pf-button
                  variant="primary"
                  type="button"
                  :disabled="sendingMessage || !newMessageBody.trim()"
                  @click="sendMessage"
                >
                  {{ sendingMessage ? "Sending…" : "Send" }}
                </pf-button>
              </pf-form>
            </div>
          </div>
        </div>
      </pf-card-body>
    </pf-card>

    <pf-modal
      v-if="inviteMaterial"
      :open="Boolean(inviteMaterial)"
      title="Invite link"
      variant="medium"
      @update:open="(open) => (!open ? dismissInviteMaterial() : undefined)"
    >
      <pf-content>
        <p class="muted">
          Share this link with the invitee.
          <span v-if="inviteMaterial.email_sent === true">Email sent.</span>
          <span v-else-if="inviteMaterial.email_sent === false">No email sent.</span>
        </p>
      </pf-content>
      <pf-form>
        <pf-form-group label="Invite URL" field-id="invite-url">
          <pf-textarea id="invite-url" :model-value="inviteMaterial.full_invite_url" rows="2" readonly />
        </pf-form-group>
        <div class="invite-copy-row">
          <pf-button type="button" variant="secondary" @click="copyInviteText(inviteMaterial.full_invite_url)">
            Copy URL
          </pf-button>
          <span class="muted">{{ inviteClipboardStatus }}</span>
        </div>

        <pf-expandable-section toggle-text-collapsed="Token (advanced)" toggle-text-expanded="Hide token">
          <pf-form-group label="Token" field-id="invite-token">
            <pf-textarea id="invite-token" :model-value="inviteMaterial.token" rows="2" readonly />
          </pf-form-group>
          <pf-button type="button" variant="secondary" @click="copyInviteText(inviteMaterial.token)">Copy token</pf-button>
        </pf-expandable-section>
      </pf-form>
      <template #footer>
        <pf-button type="button" variant="primary" @click="dismissInviteMaterial">Done</pf-button>
      </template>
    </pf-modal>

    <TeamPersonModal
      v-model:open="personModalOpen"
      :org-id="context.orgId"
      :person="person"
      :can-manage="canManage"
      :initial-section="personModalInitialSection"
      @saved="onPersonSaved"
      @invite-material="showInviteMaterial"
    />
  </div>
</template>

<style scoped>
.stack {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.header {
  display: flex;
  gap: 1rem;
  justify-content: space-between;
  align-items: flex-start;
}

.header-left {
  display: flex;
  gap: 0.75rem;
  align-items: center;
}

.header-text {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
}

.header-meta {
  display: flex;
  gap: 0.5rem;
  align-items: center;
}

.header-right {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  align-items: flex-end;
}

.header-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  justify-content: flex-end;
}

.invite-copy-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  align-items: center;
}

.muted {
  color: var(--pf-v6-global--Color--200);
}

.small {
  font-size: 0.85rem;
}

.loading-row {
  display: flex;
  justify-content: center;
  padding: 1rem 0;
}

.details-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1rem;
}

.details-stack {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.avatar-row {
  display: flex;
  gap: 1rem;
  align-items: flex-start;
}

.avatar-actions {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  flex: 1;
}

.avatar-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.detail.full {
  grid-column: 1 / -1;
}

.detail .label {
  font-size: 0.85rem;
  color: var(--pf-v6-global--Color--200);
}

.detail .value {
  margin-top: 0.25rem;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.messages-grid {
  display: grid;
  grid-template-columns: 360px minmax(0, 1fr);
  gap: 1rem;
  align-items: start;
}

.thread-create {
  display: flex;
  gap: 0.5rem;
  align-items: end;
  margin-bottom: 1rem;
}

.thread-row {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
}

.thread-title {
  font-weight: 600;
}

.thread-item.selected :deep(.pf-v6-c-data-list__item-row) {
  background: var(--pf-v6-global--BackgroundColor--200);
}

.thread-stack {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.thread-header {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  align-items: baseline;
}

.message-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  padding-right: 0.25rem;
  max-height: 420px;
  overflow: auto;
}

.message-meta {
  margin-bottom: 0.25rem;
}

.message-body :deep(p) {
  margin: 0.25rem 0;
}

.composer {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

@media (max-width: 1100px) {
  .messages-grid {
    grid-template-columns: 1fr;
  }
}
</style>
