import json

from django.contrib.auth import get_user_model
from django.test import TestCase

from api_keys.services import create_api_key
from audit.models import AuditEvent

from .models import Org, OrgInvite, OrgMembership, Person


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
        invite_url = invite_json["invite_url"]
        invite_id = invite_json["invite"]["id"]

        self.assertTrue(invite_url.startswith("/invite/accept?token="))
        self.assertIn(raw_token, invite_url)
        self.assertNotIn("://", invite_url)

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

    def test_admin_can_list_org_memberships_and_filter_by_role(self) -> None:
        pm = get_user_model().objects.create_user(email="pm@example.com", password="pw")
        client_user = get_user_model().objects.create_user(
            email="client@example.com", password="pw", display_name="Client"
        )
        member_user = get_user_model().objects.create_user(
            email="member@example.com", password="pw"
        )
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=pm, role=OrgMembership.Role.PM)
        OrgMembership.objects.create(org=org, user=client_user, role=OrgMembership.Role.CLIENT)
        OrgMembership.objects.create(org=org, user=member_user, role=OrgMembership.Role.MEMBER)

        self.client.force_login(pm)

        response = self.client.get(f"/api/orgs/{org.id}/memberships?role=client")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["memberships"]), 1)
        row = payload["memberships"][0]
        self.assertEqual(row["role"], OrgMembership.Role.CLIENT)
        self.assertEqual(row["user"]["email"], client_user.email)
        self.assertEqual(row["user"]["display_name"], "Client")

        invalid_role = self.client.get(f"/api/orgs/{org.id}/memberships?role=unknown")
        self.assertEqual(invalid_role.status_code, 400)

    def test_org_memberships_list_forbids_non_pm_admin_and_api_keys(self) -> None:
        pm = get_user_model().objects.create_user(email="pm@example.com", password="pw")
        client_user = get_user_model().objects.create_user(
            email="client@example.com", password="pw"
        )
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=pm, role=OrgMembership.Role.PM)
        OrgMembership.objects.create(org=org, user=client_user, role=OrgMembership.Role.CLIENT)

        client_c = self.client_class()
        client_c.force_login(client_user)
        response = client_c.get(f"/api/orgs/{org.id}/memberships?role=client")
        self.assertEqual(response.status_code, 403)

        _key, minted = create_api_key(org=org, owner_user=pm, name="Automation", scopes=["read", "write"], created_by_user=pm)
        api_key_list = self.client.get(
            f"/api/orgs/{org.id}/memberships?role=client",
            HTTP_AUTHORIZATION=f"Bearer {minted.token}",
        )
        self.assertEqual(api_key_list.status_code, 403)

    def test_admin_can_update_member_profile_and_availability_fields(self) -> None:
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
            {
                "display_name": "New Name",
                "title": "Engineer",
                "skills": ["python", "django", "python"],
                "bio": "Short bio",
                "availability_status": OrgMembership.AvailabilityStatus.AVAILABLE,
                "availability_hours_per_week": 20,
                "availability_next_available_at": "2026-02-20",
                "availability_notes": "Limited next week",
            },
        )
        self.assertEqual(response.status_code, 200)

        user.refresh_from_db()
        membership.refresh_from_db()

        self.assertEqual(user.display_name, "New Name")
        self.assertEqual(membership.title, "Engineer")
        self.assertEqual(membership.skills, ["python", "django"])
        self.assertEqual(membership.bio, "Short bio")
        self.assertEqual(membership.availability_status, OrgMembership.AvailabilityStatus.AVAILABLE)
        self.assertEqual(membership.availability_hours_per_week, 20)
        self.assertEqual(membership.availability_next_available_at.isoformat(), "2026-02-20")
        self.assertEqual(membership.availability_notes, "Limited next week")

        list_response = self.client.get(f"/api/orgs/{org.id}/memberships")
        self.assertEqual(list_response.status_code, 200)
        payload = list_response.json()

        row = next((m for m in payload["memberships"] if m["id"] == str(membership.id)), None)
        self.assertIsNotNone(row)
        assert row is not None

        self.assertEqual(row["user"]["display_name"], "New Name")
        self.assertEqual(row["title"], "Engineer")
        self.assertEqual(row["skills"], ["python", "django"])
        self.assertEqual(row["bio"], "Short bio")
        self.assertEqual(row["availability_status"], OrgMembership.AvailabilityStatus.AVAILABLE)
        self.assertEqual(row["availability_hours_per_week"], 20)
        self.assertEqual(row["availability_next_available_at"], "2026-02-20")
        self.assertEqual(row["availability_notes"], "Limited next week")

        event = AuditEvent.objects.get(org=org, event_type="org_membership.updated")
        self.assertIn("fields_changed", event.metadata)
        self.assertIn("availability_status", event.metadata["fields_changed"])

    def test_admin_can_create_list_and_update_people_records(self) -> None:
        admin = get_user_model().objects.create_user(email="admin@example.com", password="pw")
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=admin, role=OrgMembership.Role.ADMIN)

        self.client.force_login(admin)

        create_resp = self._post_json(
            f"/api/orgs/{org.id}/people",
            {
                "full_name": "Alice Example",
                "email": "alice@example.com",
                "timezone": "America/New_York",
                "skills": ["python", "django"],
            },
        )
        self.assertEqual(create_resp.status_code, 200)
        person_id = create_resp.json()["person"]["id"]

        list_resp = self.client.get(f"/api/orgs/{org.id}/people")
        self.assertEqual(list_resp.status_code, 200)
        people = list_resp.json()["people"]
        self.assertTrue(any(p["id"] == person_id for p in people))

        patch_resp = self._patch_json(
            f"/api/orgs/{org.id}/people/{person_id}",
            {"title": "Engineer", "notes": "Great candidate"},
        )
        self.assertEqual(patch_resp.status_code, 200)
        patched = patch_resp.json()["person"]
        self.assertEqual(patched["title"], "Engineer")
        self.assertEqual(patched["notes"], "Great candidate")

    def test_invites_list_revoke_resend_and_accept_links_person(self) -> None:
        admin = get_user_model().objects.create_user(email="admin@example.com", password="pw")
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=admin, role=OrgMembership.Role.ADMIN)

        self.client.force_login(admin)

        person = Person.objects.create(org=org, full_name="Invitee", email="invitee@example.com")

        invite_resp = self._post_json(
            f"/api/orgs/{org.id}/people/{person.id}/invite",
            {"role": OrgMembership.Role.MEMBER, "message": "Welcome"},
        )
        self.assertEqual(invite_resp.status_code, 200)
        invite_id = invite_resp.json()["invite"]["id"]
        token = invite_resp.json()["token"]

        active_list = self.client.get(f"/api/orgs/{org.id}/invites?status=active")
        self.assertEqual(active_list.status_code, 200)
        active_ids = [row["id"] for row in active_list.json()["invites"]]
        self.assertIn(invite_id, active_ids)

        resend_resp = self._post_json(
            f"/api/orgs/{org.id}/invites/{invite_id}/resend",
            {},
        )
        self.assertEqual(resend_resp.status_code, 200)
        new_invite_id = resend_resp.json()["invite"]["id"]
        new_token = resend_resp.json()["token"]
        self.assertNotEqual(invite_id, new_invite_id)
        self.assertNotEqual(token, new_token)

        accept_client = self.client_class()
        accept_resp = self._post_json(
            "/api/invites/accept",
            {"token": new_token, "password": "pw2", "display_name": "Invitee"},
            client=accept_client,
        )
        self.assertEqual(accept_resp.status_code, 200)
        accept_payload = accept_resp.json()
        self.assertIn("membership", accept_payload)
        self.assertIn("person", accept_payload)
        self.assertEqual(accept_payload["person"]["id"], str(person.id))

        user = get_user_model().objects.get(email="invitee@example.com")
        person.refresh_from_db()
        self.assertEqual(person.user_id, user.id)

        # Revoking an accepted invite should be idempotent but not change acceptance.
        revoke_resp = self._post_json(
            f"/api/orgs/{org.id}/invites/{new_invite_id}/revoke",
            {},
        )
        self.assertEqual(revoke_resp.status_code, 200)
