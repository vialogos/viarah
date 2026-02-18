import json
import os
from unittest import mock

from cryptography.fernet import Fernet
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from audit.models import AuditEvent
from identity.models import Org, OrgMembership
from work_items.models import Epic, Project, Task

from .gitlab import GitLabHttpError
from .models import GitLabWebhookDelivery, OrgGitLabIntegration, TaskGitLabLink
from .services import decrypt_token, encrypt_token, hash_webhook_secret
from .tasks import process_gitlab_webhook_delivery, refresh_gitlab_link_metadata


class GitLabIntegrationApiTests(TestCase):
    def _post_json(self, url: str, payload: dict, *, client=None):
        active_client = client or self.client
        return active_client.post(url, data=json.dumps(payload), content_type="application/json")

    def _patch_json(self, url: str, payload: dict, *, client=None):
        active_client = client or self.client
        return active_client.patch(url, data=json.dumps(payload), content_type="application/json")

    def _create_org_with_user(self, *, role: str, email: str) -> tuple[object, Org]:
        user = get_user_model().objects.create_user(email=email, password="pw")
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=user, role=role)
        return user, org

    def _create_task(self, *, org: Org) -> Task:
        project = Project.objects.create(org=org, name="P")
        epic = Epic.objects.create(project=project, title="E")
        return Task.objects.create(epic=epic, title="T")

    def test_org_gitlab_settings_requires_admin_or_pm(self) -> None:
        admin, org = self._create_org_with_user(
            role=OrgMembership.Role.ADMIN, email="a@example.com"
        )
        member, _ = self._create_org_with_user(
            role=OrgMembership.Role.MEMBER, email="m@example.com"
        )

        self.client.force_login(member)
        response = self.client.get(f"/api/orgs/{org.id}/integrations/gitlab")
        self.assertEqual(response.status_code, 403)

        self.client.force_login(admin)
        response = self.client.get(f"/api/orgs/{org.id}/integrations/gitlab")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["gitlab"]["has_token"], False)

    def test_org_gitlab_settings_token_is_encrypted_and_not_returned(self) -> None:
        admin, org = self._create_org_with_user(
            role=OrgMembership.Role.ADMIN, email="a2@example.com"
        )
        self.client.force_login(admin)

        key = Fernet.generate_key().decode("utf-8")
        with mock.patch.dict(os.environ, {"VIA_RAH_ENCRYPTION_KEY": key}):
            response = self._patch_json(
                f"/api/orgs/{org.id}/integrations/gitlab",
                {"base_url": "https://gitlab.com", "token": "glpat-not-real"},
            )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["gitlab"]["has_token"])
        self.assertNotIn("token", payload["gitlab"])

        integration = OrgGitLabIntegration.objects.get(org=org)
        self.assertNotEqual(integration.token_ciphertext, "glpat-not-real")
        with mock.patch.dict(os.environ, {"VIA_RAH_ENCRYPTION_KEY": key}):
            self.assertEqual(decrypt_token(integration.token_ciphertext or ""), "glpat-not-real")

        event = AuditEvent.objects.get(org=org, event_type="integration.gitlab.updated")
        for key_name in event.metadata.keys():
            self.assertNotIn("token", key_name.lower())
            self.assertNotIn("secret", key_name.lower())

    def test_org_gitlab_settings_rejects_invalid_encryption_key(self) -> None:
        admin, org = self._create_org_with_user(
            role=OrgMembership.Role.ADMIN, email="a4@example.com"
        )
        self.client.force_login(admin)

        with mock.patch.dict(os.environ, {"VIA_RAH_ENCRYPTION_KEY": "not-a-key"}):
            response = self._patch_json(
                f"/api/orgs/{org.id}/integrations/gitlab",
                {"base_url": "https://gitlab.com", "token": "glpat-not-real"},
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("VIA_RAH_ENCRYPTION_KEY", response.json()["error"])
        self.assertIn("invalid", response.json()["error"])
        self.assertEqual(OrgGitLabIntegration.objects.filter(org=org).count(), 0)

    def test_gitlab_validate_requires_admin_or_pm(self) -> None:
        admin, org = self._create_org_with_user(
            role=OrgMembership.Role.ADMIN, email="a5@example.com"
        )
        member, _org2 = self._create_org_with_user(
            role=OrgMembership.Role.MEMBER, email="m2@example.com"
        )

        self.client.force_login(member)
        response = self.client.post(f"/api/orgs/{org.id}/integrations/gitlab/validate")
        self.assertEqual(response.status_code, 403)

        self.client.force_login(admin)
        response = self.client.post(f"/api/orgs/{org.id}/integrations/gitlab/validate")
        self.assertEqual(response.status_code, 200)

    def test_gitlab_validate_returns_not_validated_for_missing_integration(self) -> None:
        admin, org = self._create_org_with_user(
            role=OrgMembership.Role.ADMIN, email="a6@example.com"
        )
        self.client.force_login(admin)

        response = self.client.post(f"/api/orgs/{org.id}/integrations/gitlab/validate")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "not_validated")
        self.assertEqual(response.json()["error_code"], "missing_integration")

    def test_gitlab_validate_returns_not_validated_for_missing_token(self) -> None:
        admin, org = self._create_org_with_user(
            role=OrgMembership.Role.ADMIN, email="a7@example.com"
        )
        OrgGitLabIntegration.objects.create(org=org, base_url="https://gitlab.com")
        self.client.force_login(admin)

        response = self.client.post(f"/api/orgs/{org.id}/integrations/gitlab/validate")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "not_validated")
        self.assertEqual(response.json()["error_code"], "missing_token")

    def test_gitlab_validate_returns_invalid_for_auth_errors(self) -> None:
        admin, org = self._create_org_with_user(
            role=OrgMembership.Role.ADMIN, email="a8@example.com"
        )
        self.client.force_login(admin)

        key = Fernet.generate_key().decode("utf-8")
        with mock.patch.dict(os.environ, {"VIA_RAH_ENCRYPTION_KEY": key}):
            OrgGitLabIntegration.objects.create(
                org=org,
                base_url="https://gitlab.com",
                token_ciphertext=encrypt_token("tok"),
            )

        with (
            mock.patch.dict(os.environ, {"VIA_RAH_ENCRYPTION_KEY": key}),
            mock.patch(
                "integrations.views.GitLabClient.get_user",
                side_effect=GitLabHttpError(status_code=401, body="", headers={}),
            ),
        ):
            response = self.client.post(f"/api/orgs/{org.id}/integrations/gitlab/validate")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "invalid")
        self.assertEqual(response.json()["error_code"], "auth_error")

    def test_gitlab_validate_returns_valid_for_success(self) -> None:
        admin, org = self._create_org_with_user(
            role=OrgMembership.Role.ADMIN, email="a9@example.com"
        )
        self.client.force_login(admin)

        key = Fernet.generate_key().decode("utf-8")
        with mock.patch.dict(os.environ, {"VIA_RAH_ENCRYPTION_KEY": key}):
            OrgGitLabIntegration.objects.create(
                org=org,
                base_url="https://gitlab.com",
                token_ciphertext=encrypt_token("tok"),
            )

        with (
            mock.patch.dict(os.environ, {"VIA_RAH_ENCRYPTION_KEY": key}),
            mock.patch("integrations.views.GitLabClient.get_user", return_value={"id": 1}),
        ):
            response = self.client.post(f"/api/orgs/{org.id}/integrations/gitlab/validate")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "valid")
        self.assertIsNone(response.json()["error_code"])

    def test_task_gitlab_links_crud_and_rbac_includes_delete(self) -> None:
        pm, org = self._create_org_with_user(role=OrgMembership.Role.PM, email="pm@example.com")
        client_user = get_user_model().objects.create_user(email="c@example.com", password="pw")
        OrgMembership.objects.create(org=org, user=client_user, role=OrgMembership.Role.CLIENT)

        task = self._create_task(org=org)
        OrgGitLabIntegration.objects.create(org=org, base_url="https://gitlab.com")

        self.client.force_login(client_user)
        forbidden = self.client.get(f"/api/orgs/{org.id}/tasks/{task.id}/gitlab-links")
        self.assertEqual(forbidden.status_code, 403)

        self.client.force_login(pm)
        with mock.patch("integrations.views.refresh_gitlab_link_metadata.delay") as delay:
            create = self._post_json(
                f"/api/orgs/{org.id}/tasks/{task.id}/gitlab-links",
                {"url": "https://gitlab.com/vialogos-labs/viarah/-/issues/12"},
            )
        self.assertEqual(create.status_code, 200)
        link_id = create.json()["link"]["id"]
        delay.assert_called()

        with mock.patch("integrations.views.refresh_gitlab_link_metadata.delay") as delay2:
            dup = self._post_json(
                f"/api/orgs/{org.id}/tasks/{task.id}/gitlab-links",
                {"url": "https://gitlab.com/vialogos-labs/viarah/-/issues/12"},
            )
        self.assertEqual(dup.status_code, 400)
        delay2.assert_not_called()

        with mock.patch("integrations.views.refresh_gitlab_link_metadata.delay") as delay3:
            listing = self.client.get(f"/api/orgs/{org.id}/tasks/{task.id}/gitlab-links")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(len(listing.json()["links"]), 1)
        delay3.assert_called()

        delete = self.client.delete(f"/api/orgs/{org.id}/tasks/{task.id}/gitlab-links/{link_id}")
        self.assertEqual(delete.status_code, 204)

        listing_after = self.client.get(f"/api/orgs/{org.id}/tasks/{task.id}/gitlab-links")
        self.assertEqual(listing_after.status_code, 200)
        self.assertEqual(len(listing_after.json()["links"]), 0)

        delete_again = self.client.delete(
            f"/api/orgs/{org.id}/tasks/{task.id}/gitlab-links/{link_id}"
        )
        self.assertEqual(delete_again.status_code, 404)

    def test_webhook_validates_secret_and_dedupes(self) -> None:
        _admin, org = self._create_org_with_user(
            role=OrgMembership.Role.ADMIN, email="a3@example.com"
        )
        OrgGitLabIntegration.objects.create(
            org=org,
            base_url="https://gitlab.com",
            webhook_secret_hash=hash_webhook_secret("whsec-not-real"),
        )

        payload = {
            "project": {"path_with_namespace": "vialogos-labs/viarah"},
            "object_attributes": {"iid": 12},
        }

        missing = self._post_json(
            f"/api/orgs/{org.id}/integrations/gitlab/webhook",
            payload,
            client=self.client,
        )
        self.assertEqual(missing.status_code, 403)

        wrong = self.client.post(
            f"/api/orgs/{org.id}/integrations/gitlab/webhook",
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_X_GITLAB_TOKEN="wrong",
            HTTP_X_GITLAB_EVENT="Issue Hook",
            HTTP_X_GITLAB_EVENT_UUID="uuid-1",
        )
        self.assertEqual(wrong.status_code, 403)

        with mock.patch("integrations.views.process_gitlab_webhook_delivery.delay") as delay2:
            ok = self.client.post(
                f"/api/orgs/{org.id}/integrations/gitlab/webhook",
                data=json.dumps(payload),
                content_type="application/json",
                HTTP_X_GITLAB_TOKEN="whsec-not-real",
                HTTP_X_GITLAB_EVENT="Issue Hook",
                HTTP_X_GITLAB_EVENT_UUID="uuid-1",
            )
            self.assertEqual(ok.status_code, 202)
            delay2.assert_called_once()

            dup = self.client.post(
                f"/api/orgs/{org.id}/integrations/gitlab/webhook",
                data=json.dumps(payload),
                content_type="application/json",
                HTTP_X_GITLAB_TOKEN="whsec-not-real",
                HTTP_X_GITLAB_EVENT="Issue Hook",
                HTTP_X_GITLAB_EVENT_UUID="uuid-1",
            )
            self.assertEqual(dup.status_code, 202)
            self.assertEqual(dup.json()["status"], "duplicate")

        self.assertEqual(
            GitLabWebhookDelivery.objects.filter(org=org, event_uuid="uuid-1").count(), 1
        )


class GitLabIntegrationTaskTests(TestCase):
    def test_refresh_updates_cache_and_handles_rate_limit(self) -> None:
        user = get_user_model().objects.create_user(email="t@example.com", password="pw")
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=user, role=OrgMembership.Role.ADMIN)
        project = Project.objects.create(org=org, name="P")
        epic = Epic.objects.create(project=project, title="E")
        task = Task.objects.create(epic=epic, title="T")

        key = Fernet.generate_key().decode("utf-8")
        with mock.patch.dict(os.environ, {"VIA_RAH_ENCRYPTION_KEY": key}):
            integration = OrgGitLabIntegration.objects.create(
                org=org, base_url="https://gitlab.com", token_ciphertext=encrypt_token("tok")
            )
        self.assertIsNotNone(integration)

        link = TaskGitLabLink.objects.create(
            task=task,
            web_url="https://gitlab.com/vialogos-labs/viarah/-/issues/12",
            project_path="vialogos-labs/viarah",
            gitlab_type=TaskGitLabLink.GitLabType.ISSUE,
            gitlab_iid=12,
        )

        with (
            mock.patch.dict(os.environ, {"VIA_RAH_ENCRYPTION_KEY": key}),
            mock.patch(
                "integrations.tasks.GitLabClient.get_issue",
                return_value={
                    "title": "T",
                    "state": "opened",
                    "labels": ["a"],
                    "assignees": [{"username": "u", "name": "User"}],
                    "participants": [{"id": 1, "username": "u", "name": "User"}],
                },
            ),
        ):
            refresh_gitlab_link_metadata(str(link.id))

        link.refresh_from_db()
        self.assertEqual(link.cached_title, "T")
        self.assertEqual(link.cached_state, "opened")
        self.assertEqual(link.cached_labels, ["a"])
        self.assertEqual(link.cached_assignees, [{"username": "u", "name": "User"}])
        self.assertEqual(link.cached_participants, [{"id": 1, "username": "u", "name": "User"}])
        self.assertIsNotNone(link.last_synced_at)
        self.assertEqual(link.last_sync_error_code, "")

        now = timezone.now()
        with (
            mock.patch.dict(os.environ, {"VIA_RAH_ENCRYPTION_KEY": key}),
            mock.patch(
                "integrations.tasks.GitLabClient.get_issue",
                side_effect=GitLabHttpError(status_code=429, body="", headers={"Retry-After": "5"}),
            ),
        ):
            refresh_gitlab_link_metadata(str(link.id))

        link.refresh_from_db()
        self.assertEqual(link.last_sync_error_code, "rate_limited")
        self.assertIsNotNone(link.rate_limited_until)
        self.assertGreater(link.rate_limited_until, now)

    def test_refresh_handles_invalid_encryption_key(self) -> None:
        user = get_user_model().objects.create_user(email="t2@example.com", password="pw")
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=user, role=OrgMembership.Role.ADMIN)
        project = Project.objects.create(org=org, name="P")
        epic = Epic.objects.create(project=project, title="E")
        task = Task.objects.create(epic=epic, title="T")

        key = Fernet.generate_key().decode("utf-8")
        with mock.patch.dict(os.environ, {"VIA_RAH_ENCRYPTION_KEY": key}):
            integration = OrgGitLabIntegration.objects.create(
                org=org, base_url="https://gitlab.com", token_ciphertext=encrypt_token("tok")
            )
        self.assertIsNotNone(integration)

        link = TaskGitLabLink.objects.create(
            task=task,
            web_url="https://gitlab.com/vialogos-labs/viarah/-/issues/12",
            project_path="vialogos-labs/viarah",
            gitlab_type=TaskGitLabLink.GitLabType.ISSUE,
            gitlab_iid=12,
        )

        with mock.patch.dict(os.environ, {"VIA_RAH_ENCRYPTION_KEY": "not-a-key"}):
            refresh_gitlab_link_metadata(str(link.id))

        link.refresh_from_db()
        self.assertEqual(link.last_sync_error_code, "encryption_key_invalid")

    def test_process_webhook_delivery_enqueues_refresh(self) -> None:
        user = get_user_model().objects.create_user(email="w@example.com", password="pw")
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=user, role=OrgMembership.Role.ADMIN)
        project = Project.objects.create(org=org, name="P")
        epic = Epic.objects.create(project=project, title="E")
        task = Task.objects.create(epic=epic, title="T")

        link = TaskGitLabLink.objects.create(
            task=task,
            web_url="https://gitlab.com/vialogos-labs/viarah/-/issues/12",
            project_path="vialogos-labs/viarah",
            gitlab_type=TaskGitLabLink.GitLabType.ISSUE,
            gitlab_iid=12,
        )
        delivery = GitLabWebhookDelivery.objects.create(
            org=org,
            event_uuid="uuid-2",
            event_type="Issue Hook",
            project_path="vialogos-labs/viarah",
            gitlab_type=TaskGitLabLink.GitLabType.ISSUE,
            gitlab_iid=12,
            payload_sha256="0" * 64,
        )

        with mock.patch("integrations.tasks.refresh_gitlab_link_metadata.delay") as delay:
            process_gitlab_webhook_delivery(str(delivery.id))
            delay.assert_called_once_with(str(link.id))

        delivery.refresh_from_db()
        self.assertEqual(delivery.status, GitLabWebhookDelivery.Status.PROCESSED)
        self.assertIsNotNone(delivery.processed_at)
