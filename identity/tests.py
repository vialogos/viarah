import json

from django.contrib.auth import get_user_model
from django.test import TestCase

from audit.models import AuditEvent

from .models import Org, OrgInvite, OrgMembership


class IdentityApiTests(TestCase):
    def _post_json(self, url: str, payload: dict, *, client=None):
        active_client = client or self.client
        return active_client.post(url, data=json.dumps(payload), content_type="application/json")

    def _patch_json(self, url: str, payload: dict, *, client=None):
        active_client = client or self.client
        return active_client.patch(url, data=json.dumps(payload), content_type="application/json")

    def test_cross_org_access_is_forbidden(self) -> None:
        user = get_user_model().objects.create_user(email="a@example.com", password="pw")
        org_a = Org.objects.create(name="Org A")
        org_b = Org.objects.create(name="Org B")
        OrgMembership.objects.create(org=org_a, user=user, role=OrgMembership.Role.ADMIN)

        self.client.force_login(user)

        response = self.client.get(f"/api/orgs/{org_b.id}/audit-events")
        self.assertEqual(response.status_code, 403)

        response = self._post_json(
            f"/api/orgs/{org_b.id}/invites",
            {"email": "b@example.com", "role": OrgMembership.Role.MEMBER},
        )
        self.assertEqual(response.status_code, 403)

    def test_login_returns_me_payload(self) -> None:
        user = get_user_model().objects.create_user(email="login@example.com", password="pw")
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=user, role=OrgMembership.Role.ADMIN)

        response = self._post_json("/api/auth/login", {"email": user.email, "password": "pw"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual(payload["user"]["email"], user.email)
        self.assertEqual(len(payload["memberships"]), 1)
        self.assertEqual(payload["memberships"][0]["org"]["id"], str(org.id))

    def test_member_cannot_create_invites_or_change_roles(self) -> None:
        user = get_user_model().objects.create_user(email="member@example.com", password="pw")
        target = get_user_model().objects.create_user(email="target@example.com", password="pw")
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=user, role=OrgMembership.Role.MEMBER)
        membership = OrgMembership.objects.create(
            org=org, user=target, role=OrgMembership.Role.MEMBER
        )

        self.client.force_login(user)

        response = self._post_json(
            f"/api/orgs/{org.id}/invites",
            {"email": "invitee@example.com", "role": OrgMembership.Role.CLIENT},
        )
        self.assertEqual(response.status_code, 403)

        response = self._patch_json(
            f"/api/orgs/{org.id}/memberships/{membership.id}",
            {"role": OrgMembership.Role.PM},
        )
        self.assertEqual(response.status_code, 403)

    def test_invite_accept_creates_membership_and_audit_events(self) -> None:
        admin = get_user_model().objects.create_user(email="admin@example.com", password="pw")
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=admin, role=OrgMembership.Role.ADMIN)

        self.client.force_login(admin)

        invite_response = self._post_json(
            f"/api/orgs/{org.id}/invites",
            {"email": "invitee@example.com", "role": OrgMembership.Role.MEMBER},
        )
        self.assertEqual(invite_response.status_code, 200)
        invite_json = invite_response.json()
        raw_token = invite_json["token"]
        invite_id = invite_json["invite"]["id"]

        invite = OrgInvite.objects.get(id=invite_id)
        self.assertNotEqual(invite.token_hash, raw_token)
        self.assertEqual(len(invite.token_hash), 64)

        created_event = AuditEvent.objects.get(org=org, event_type="org_invite.created")
        self.assertNotIn("token", created_event.metadata)

        accept_client = self.client_class()
        accept_response = self._post_json(
            "/api/invites/accept",
            {"token": raw_token, "password": "pw2", "display_name": "Invitee"},
            client=accept_client,
        )
        self.assertEqual(accept_response.status_code, 200)

        user = get_user_model().objects.get(email="invitee@example.com")
        membership = OrgMembership.objects.get(org=org, user=user)
        self.assertEqual(membership.role, OrgMembership.Role.MEMBER)

        invite.refresh_from_db()
        self.assertIsNotNone(invite.accepted_at)

        event_types = set(AuditEvent.objects.filter(org=org).values_list("event_type", flat=True))
        self.assertIn("org_invite.created", event_types)
        self.assertIn("org_invite.accepted", event_types)
        self.assertIn("org_membership.created", event_types)

        accept_again = self._post_json(
            "/api/invites/accept",
            {"token": raw_token, "password": "pw2", "display_name": "Invitee"},
            client=accept_client,
        )
        self.assertEqual(accept_again.status_code, 400)

    def test_admin_can_change_role_and_audit_is_written(self) -> None:
        admin = get_user_model().objects.create_user(email="admin@example.com", password="pw")
        user = get_user_model().objects.create_user(email="user@example.com", password="pw")
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=admin, role=OrgMembership.Role.ADMIN)
        membership = OrgMembership.objects.create(
            org=org, user=user, role=OrgMembership.Role.MEMBER
        )

        self.client.force_login(admin)
        response = self._patch_json(
            f"/api/orgs/{org.id}/memberships/{membership.id}",
            {"role": OrgMembership.Role.PM},
        )
        self.assertEqual(response.status_code, 200)

        membership.refresh_from_db()
        self.assertEqual(membership.role, OrgMembership.Role.PM)

        event = AuditEvent.objects.get(org=org, event_type="org_membership.role_changed")
        self.assertEqual(event.metadata["old_role"], OrgMembership.Role.MEMBER)
        self.assertEqual(event.metadata["new_role"], OrgMembership.Role.PM)
