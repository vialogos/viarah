import json

from django.contrib.auth import get_user_model
from django.test import TestCase

from api_keys.services import create_api_key
from audit.models import AuditEvent
from identity.models import Org, OrgMembership


class ApiKeysTests(TestCase):
    def _post_json(self, url: str, payload: dict, *, client=None):
        active_client = client or self.client
        return active_client.post(url, data=json.dumps(payload), content_type="application/json")

    def test_list_rejects_invalid_org_id(self) -> None:
        user = get_user_model().objects.create_user(email="admin3@example.com", password="pw")
        self.client.force_login(user)

        response = self.client.get("/api/api-keys?org_id=not-a-uuid")
        self.assertEqual(response.status_code, 400)

    def test_mint_list_revoke_rotate_and_me_auth(self) -> None:
        user = get_user_model().objects.create_user(email="admin@example.com", password="pw")
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=user, role=OrgMembership.Role.ADMIN)

        self.client.force_login(user)

        create_response = self._post_json(
            "/api/api-keys",
            {"org_id": str(org.id), "name": "Automation Key", "scopes": ["read", "write"]},
        )
        self.assertEqual(create_response.status_code, 200)
        create_payload = create_response.json()
        token = create_payload["token"]
        api_key_id = create_payload["api_key"]["id"]
        self.assertTrue(token.startswith("vrak_"))

        list_response = self.client.get(f"/api/api-keys?org_id={org.id}")
        self.assertEqual(list_response.status_code, 200)
        list_payload = list_response.json()
        self.assertEqual(len(list_payload["api_keys"]), 1)
        self.assertNotIn("token", list_payload["api_keys"][0])
        self.assertNotIn("secret_hash", list_payload["api_keys"][0])

        me_response = self.client.get("/api/me", HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(me_response.status_code, 200)
        me_payload = me_response.json()
        self.assertEqual(me_payload["principal_type"], "api_key")
        self.assertEqual(me_payload["api_key_id"], api_key_id)
        self.assertEqual(me_payload["org_id"], str(org.id))

        revoke_response = self._post_json(f"/api/api-keys/{api_key_id}/revoke", {})
        self.assertEqual(revoke_response.status_code, 200)

        revoked_me = self.client.get("/api/me", HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(revoked_me.status_code, 401)

        rotate_response = self._post_json(f"/api/api-keys/{api_key_id}/rotate", {})
        self.assertEqual(rotate_response.status_code, 400)

    def test_me_allows_api_key_without_org_membership(self) -> None:
        user = get_user_model().objects.create_user(email="unaffiliated@example.com", password="pw")
        org = Org.objects.create(name="Org")

        _key, minted = create_api_key(
            org=org,
            owner_user=user,
            name="Automation Key",
            scopes=["read"],
            created_by_user=user,
        )

        response = self.client.get("/api/me", HTTP_AUTHORIZATION=f"Bearer {minted.token}")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["principal_type"], "api_key")
        self.assertEqual(payload["org_id"], str(org.id))
        self.assertEqual(payload["owner_user_id"], str(user.id))
        self.assertEqual(payload["user"]["email"], user.email)
        self.assertEqual(payload["memberships"], [])

    def test_me_requires_read_scope(self) -> None:
        user = get_user_model().objects.create_user(email="admin4@example.com", password="pw")
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=user, role=OrgMembership.Role.ADMIN)

        self.client.force_login(user)

        create_response = self._post_json(
            "/api/api-keys",
            {"org_id": str(org.id), "name": "Write-only Key", "scopes": ["write"]},
        )
        self.assertEqual(create_response.status_code, 200)
        token = create_response.json()["token"]

        response = self.client.get("/api/me", HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(response.status_code, 403)

    def test_rotate_invalidates_old_token(self) -> None:
        user = get_user_model().objects.create_user(email="admin2@example.com", password="pw")
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=user, role=OrgMembership.Role.ADMIN)

        self.client.force_login(user)

        create_response = self._post_json(
            "/api/api-keys",
            {"org_id": str(org.id), "name": "Automation Key"},
        )
        self.assertEqual(create_response.status_code, 200)
        create_payload = create_response.json()
        old_token = create_payload["token"]
        api_key_id = create_payload["api_key"]["id"]

        rotate_response = self._post_json(f"/api/api-keys/{api_key_id}/rotate", {})
        self.assertEqual(rotate_response.status_code, 200)
        rotate_payload = rotate_response.json()
        new_token = rotate_payload["token"]
        self.assertNotEqual(old_token, new_token)

        old_me = self.client.get("/api/me", HTTP_AUTHORIZATION=f"Bearer {old_token}")
        self.assertEqual(old_me.status_code, 401)

        new_me = self.client.get("/api/me", HTTP_AUTHORIZATION=f"Bearer {new_token}")
        self.assertEqual(new_me.status_code, 200)

        event_types = set(AuditEvent.objects.filter(org=org).values_list("event_type", flat=True))
        self.assertIn("api_key.created", event_types)
        self.assertIn("api_key.rotated", event_types)
