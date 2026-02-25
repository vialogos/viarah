import json

from django.contrib.auth import get_user_model
from django.test import TestCase

from identity.models import Org, OrgMembership


class TemplatesApiTests(TestCase):
    def _post_json(self, url: str, payload: dict, *, client=None):
        active_client = client or self.client
        return active_client.post(url, data=json.dumps(payload), content_type="application/json")

    def test_template_versioning_retains_prior_versions(self) -> None:
        pm = get_user_model().objects.create_user(email="pm@example.com", password="pw")
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=pm, role=OrgMembership.Role.PM)

        self.client.force_login(pm)

        create_resp = self._post_json(
            f"/api/orgs/{org.id}/templates",
            {"type": "report", "name": "Weekly Status", "body": "# Weekly Status v1"},
        )
        self.assertEqual(create_resp.status_code, 200)
        template_id = create_resp.json()["template"]["id"]
        v1_id = create_resp.json()["template"]["current_version_id"]

        v2_resp = self._post_json(
            f"/api/orgs/{org.id}/templates/{template_id}/versions",
            {"body": "# Weekly Status v2"},
        )
        self.assertEqual(v2_resp.status_code, 200)
        v2_id = v2_resp.json()["template"]["current_version_id"]
        self.assertNotEqual(v1_id, v2_id)

        detail = self.client.get(f"/api/orgs/{org.id}/templates/{template_id}")
        self.assertEqual(detail.status_code, 200)
        versions = detail.json()["versions"]
        self.assertEqual(len(versions), 2)

        version_ids = {v["id"] for v in versions}
        self.assertIn(v1_id, version_ids)
        self.assertIn(v2_id, version_ids)

        v1_detail = self.client.get(f"/api/orgs/{org.id}/templates/{template_id}/versions/{v1_id}")
        self.assertEqual(v1_detail.status_code, 200)
        self.assertEqual(v1_detail.json()["version"]["body"], "# Weekly Status v1")

    def test_duplicate_template_name_returns_400(self) -> None:
        pm = get_user_model().objects.create_user(email="pm@example.com", password="pw")
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=pm, role=OrgMembership.Role.PM)

        self.client.force_login(pm)

        create_resp = self._post_json(
            f"/api/orgs/{org.id}/templates",
            {"type": "report", "name": "Weekly Status", "body": "# Weekly Status v1"},
        )
        self.assertEqual(create_resp.status_code, 200)

        dup_resp = self._post_json(
            f"/api/orgs/{org.id}/templates",
            {"type": "report", "name": "Weekly Status", "body": "# Weekly Status v1"},
        )
        self.assertEqual(dup_resp.status_code, 400)
        self.assertEqual(dup_resp.json()["error"], "template with this name already exists")

    def test_template_name_too_long_returns_400(self) -> None:
        pm = get_user_model().objects.create_user(email="pm@example.com", password="pw")
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=pm, role=OrgMembership.Role.PM)

        self.client.force_login(pm)

        resp = self._post_json(
            f"/api/orgs/{org.id}/templates",
            {
                "type": "report",
                "name": "a" * 201,
                "body": "# Weekly Status v1",
            },
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["error"], "name is too long")

    def test_client_role_cannot_create_templates(self) -> None:
        client_user = get_user_model().objects.create_user(
            email="client@example.com", password="pw"
        )
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=client_user, role=OrgMembership.Role.CLIENT)

        self.client.force_login(client_user)

        resp = self._post_json(
            f"/api/orgs/{org.id}/templates",
            {"type": "report", "name": "Weekly Status", "body": "# Weekly Status"},
        )
        self.assertEqual(resp.status_code, 403)
