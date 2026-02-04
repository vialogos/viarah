import json
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from api_keys.services import create_api_key
from audit.models import AuditEvent
from identity.models import Org, OrgMembership
from work_items.models import Project


class SowsApiTests(TestCase):
    def _post_json(self, url: str, payload: dict, *, client=None):
        active_client = client or self.client
        return active_client.post(url, data=json.dumps(payload), content_type="application/json")

    def test_sow_flow_draft_send_sign_and_pdf_permissions(self) -> None:
        pm = get_user_model().objects.create_user(email="pm@example.com", password="pw")
        client_user = get_user_model().objects.create_user(
            email="client@example.com", password="pw"
        )
        other_client = get_user_model().objects.create_user(
            email="other-client@example.com", password="pw"
        )
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=pm, role=OrgMembership.Role.PM)
        OrgMembership.objects.create(org=org, user=client_user, role=OrgMembership.Role.CLIENT)
        OrgMembership.objects.create(org=org, user=other_client, role=OrgMembership.Role.CLIENT)

        project = Project.objects.create(org=org, name="Project", description="Desc")

        self.client.force_login(pm)

        template_resp = self._post_json(
            f"/api/orgs/{org.id}/templates",
            {
                "type": "sow",
                "name": "SoW v1",
                "body": "# SoW for {{ project.name }}\nClient: {{ variables.client_name }}",
            },
        )
        self.assertEqual(template_resp.status_code, 200)
        template_id = template_resp.json()["template"]["id"]

        sow_create = self._post_json(
            f"/api/orgs/{org.id}/sows",
            {
                "project_id": str(project.id),
                "template_id": template_id,
                "variables": {"client_name": "ACME"},
                "signer_user_ids": [str(client_user.id)],
            },
        )
        self.assertEqual(sow_create.status_code, 200)
        sow_id = sow_create.json()["sow"]["id"]
        version_payload = sow_create.json()["version"]
        self.assertEqual(version_payload["status"], "draft")
        self.assertIn("SoW for Project", version_payload["body_markdown"])
        self.assertIn("ACME", version_payload["body_markdown"])

        # Member/other client can't read (not assigned signer).
        other_c = self.client_class()
        other_c.force_login(other_client)
        forbidden_read = other_c.get(f"/api/orgs/{org.id}/sows/{sow_id}")
        self.assertEqual(forbidden_read.status_code, 403)

        # API key principal blocked for all endpoints.
        _key, minted = create_api_key(org=org, name="Automation", scopes=["read", "write"])
        api_key_read = self.client.get(
            f"/api/orgs/{org.id}/sows/{sow_id}", HTTP_AUTHORIZATION=f"Bearer {minted.token}"
        )
        self.assertEqual(api_key_read.status_code, 403)

        send = self._post_json(f"/api/orgs/{org.id}/sows/{sow_id}/send", {})
        self.assertEqual(send.status_code, 200)
        self.assertEqual(send.json()["version"]["status"], "pending_signature")
        self.assertIsNotNone(send.json()["version"]["content_sha256"])

        # Can't create a new version while pending signature.
        new_version_pending = self._post_json(f"/api/orgs/{org.id}/sows/{sow_id}/versions", {})
        self.assertEqual(new_version_pending.status_code, 409)

        # Assigned signer can read and respond.
        client_c = self.client_class()
        client_c.force_login(client_user)
        ok_read = client_c.get(f"/api/orgs/{org.id}/sows/{sow_id}")
        self.assertEqual(ok_read.status_code, 200)
        self.assertEqual(ok_read.json()["version"]["status"], "pending_signature")

        reject_missing_sig = self._post_json(
            f"/api/orgs/{org.id}/sows/{sow_id}/respond",
            {"decision": "approve"},
            client=client_c,
        )
        self.assertEqual(reject_missing_sig.status_code, 409)

        approve = self._post_json(
            f"/api/orgs/{org.id}/sows/{sow_id}/respond",
            {"decision": "approve", "typed_signature": "Client Name", "comment": "LGTM"},
            client=client_c,
        )
        self.assertEqual(approve.status_code, 200)
        self.assertEqual(approve.json()["version"]["status"], "signed")

        # Signer cannot request PDF; PM can.
        signer_pdf_post = client_c.post(f"/api/orgs/{org.id}/sows/{sow_id}/pdf")
        self.assertEqual(signer_pdf_post.status_code, 403)

        with patch(
            "sows.views.render_sow_version_pdf.delay",
            return_value=SimpleNamespace(id="celery-task-id"),
        ) as delay_mock:
            pdf_request = self.client.post(f"/api/orgs/{org.id}/sows/{sow_id}/pdf")
        self.assertEqual(pdf_request.status_code, 202)
        delay_mock.assert_called_once()
        self.assertEqual(pdf_request.json()["pdf"]["status"], "queued")

        pdf_download_not_ready = client_c.get(f"/api/orgs/{org.id}/sows/{sow_id}/pdf")
        self.assertEqual(pdf_download_not_ready.status_code, 409)

        event_types = set(AuditEvent.objects.filter(org=org).values_list("event_type", flat=True))
        self.assertIn("sow.created", event_types)
        self.assertIn("sow.sent", event_types)
        self.assertIn("sow.signer_approved", event_types)
        self.assertIn("sow.signed", event_types)

        # After signed, can create a new draft version and send again.
        new_version = self._post_json(
            f"/api/orgs/{org.id}/sows/{sow_id}/versions",
            {},
        )
        self.assertEqual(new_version.status_code, 200)
        self.assertEqual(new_version.json()["version"]["version"], 2)
        self.assertEqual(new_version.json()["version"]["status"], "draft")
