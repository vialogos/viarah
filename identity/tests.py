import json

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from api_keys.services import create_api_key
from audit.models import AuditEvent
from work_items.models import Project, ProjectMembership

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

    def test_auth_me_patch_updates_display_name(self) -> None:
        user = get_user_model().objects.create_user(
            email="account@example.com", password="pw", display_name="Before"
        )
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=user, role=OrgMembership.Role.MEMBER)

        self.client.force_login(user)

        resp = self._patch_json("/api/auth/me", {"display_name": "After"})
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertEqual(payload["user"]["display_name"], "After")

        user.refresh_from_db()
        self.assertEqual(user.display_name, "After")

    @override_settings(
        PUBLIC_APP_URL="https://app.example.test", DEFAULT_FROM_EMAIL="noreply@example.com"
    )
    def test_password_reset_request_and_confirm_flow(self) -> None:
        user = get_user_model().objects.create_user(email="reset@example.com", password="OldPw123!")

        mail.outbox.clear()
        resp = self._post_json("/api/auth/password-reset/request", {"email": user.email})
        self.assertEqual(resp.status_code, 204)
        self.assertEqual(len(mail.outbox), 1)

        body = mail.outbox[0].body
        self.assertIn("https://app.example.test/password-reset/confirm?uid=", body)

        start = body.find("uid=")
        self.assertNotEqual(start, -1)
        query = body[start:].strip().splitlines()[0]
        uid = ""
        token = ""
        for part in query.split("&"):
            if part.startswith("uid="):
                uid = part.split("=", 1)[1]
            elif part.startswith("token="):
                token = part.split("=", 1)[1]

        self.assertTrue(uid)
        self.assertTrue(token)

        new_password = "CorrectHorseBatteryStaple1!"
        confirm_resp = self._post_json(
            "/api/auth/password-reset/confirm",
            {"uid": uid, "token": token, "password": new_password},
        )
        self.assertEqual(confirm_resp.status_code, 204)

        user.refresh_from_db()
        self.assertTrue(user.check_password(new_password))

    def test_password_reset_request_does_not_reveal_missing_email(self) -> None:
        mail.outbox.clear()
        resp = self._post_json("/api/auth/password-reset/request", {"email": "missing@example.com"})
        self.assertEqual(resp.status_code, 204)
        self.assertEqual(len(mail.outbox), 0)

    def test_password_change_requires_session_and_current_password(self) -> None:
        user = get_user_model().objects.create_user(
            email="pwchange@example.com", password="OldPw123!"
        )

        anonymous_resp = self._post_json(
            "/api/auth/password-change",
            {"current_password": "OldPw123!", "new_password": "CorrectHorseBatteryStaple1!"},
        )
        self.assertEqual(anonymous_resp.status_code, 401)

        self.client.force_login(user)

        wrong_resp = self._post_json(
            "/api/auth/password-change",
            {"current_password": "wrong", "new_password": "CorrectHorseBatteryStaple1!"},
        )
        self.assertEqual(wrong_resp.status_code, 400)

        ok_resp = self._post_json(
            "/api/auth/password-change",
            {"current_password": "OldPw123!", "new_password": "CorrectHorseBatteryStaple1!"},
        )
        self.assertEqual(ok_resp.status_code, 204)

        user.refresh_from_db()
        self.assertTrue(user.check_password("CorrectHorseBatteryStaple1!"))

    def test_orgs_collection_lists_and_creates_orgs(self) -> None:
        user = get_user_model().objects.create_user(email="pm@example.com", password="pw")
        org_a = Org.objects.create(name="Org A")
        OrgMembership.objects.create(org=org_a, user=user, role=OrgMembership.Role.PM)

        self.client.force_login(user)

        list_resp = self.client.get("/api/orgs")
        self.assertEqual(list_resp.status_code, 200)
        payload = list_resp.json()
        self.assertEqual(len(payload["orgs"]), 1)
        self.assertEqual(payload["orgs"][0]["id"], str(org_a.id))
        self.assertEqual(payload["orgs"][0]["name"], "Org A")
        self.assertEqual(payload["orgs"][0]["role"], OrgMembership.Role.PM)
        self.assertIsNone(payload["orgs"][0]["logo_url"])

        create_resp = self._post_json("/api/orgs", {"name": "New Org"})
        self.assertEqual(create_resp.status_code, 200)
        created = create_resp.json()["org"]
        self.assertEqual(created["name"], "New Org")
        self.assertEqual(created["role"], OrgMembership.Role.ADMIN)

        org = Org.objects.get(id=created["id"])
        membership = OrgMembership.objects.get(org=org, user=user)
        self.assertEqual(membership.role, OrgMembership.Role.ADMIN)
        self.assertTrue(AuditEvent.objects.filter(org=org, event_type="org.created").exists())

    def test_platform_admin_can_list_orgs_and_manage_memberships_without_memberships(self) -> None:
        platform_admin = get_user_model().objects.create_superuser(
            email="root@example.com",
            password="pw",
        )
        target = get_user_model().objects.create_user(email="target@example.com", password="pw")

        org_a = Org.objects.create(name="Org A")
        org_b = Org.objects.create(name="Org B")
        member = get_user_model().objects.create_user(email="member@example.com", password="pw")
        OrgMembership.objects.create(org=org_a, user=member, role=OrgMembership.Role.MEMBER)

        self.client.force_login(platform_admin)

        list_resp = self.client.get("/api/orgs")
        self.assertEqual(list_resp.status_code, 200)
        payload = list_resp.json()
        self.assertEqual({row["id"] for row in payload["orgs"]}, {str(org_a.id), str(org_b.id)})
        self.assertTrue(all(row["role"] == OrgMembership.Role.ADMIN for row in payload["orgs"]))

        list_memberships = self.client.get(f"/api/orgs/{org_a.id}/memberships")
        self.assertEqual(list_memberships.status_code, 200)

        create_membership = self._post_json(
            f"/api/orgs/{org_b.id}/memberships",
            {"email": target.email, "role": OrgMembership.Role.PM},
        )
        self.assertEqual(create_membership.status_code, 201)

        membership = OrgMembership.objects.get(org=org_b, user=target)
        self.assertEqual(membership.role, OrgMembership.Role.PM)

        patch_membership = self._patch_json(
            f"/api/orgs/{org_b.id}/memberships/{membership.id}",
            {"role": OrgMembership.Role.MEMBER},
        )
        self.assertEqual(patch_membership.status_code, 200)

        membership.refresh_from_db()
        self.assertEqual(membership.role, OrgMembership.Role.MEMBER)
        self.assertTrue(
            AuditEvent.objects.filter(org=org_b, event_type="org_membership.role_changed").exists()
        )

    def test_platform_pm_can_list_all_orgs_without_memberships(self) -> None:
        platform_pm = get_user_model().objects.create_user(
            email="pm@example.com",
            password="pw",
            is_staff=True,
        )
        org_a = Org.objects.create(name="Org A")
        org_b = Org.objects.create(name="Org B")

        self.client.force_login(platform_pm)

        list_resp = self.client.get("/api/orgs")
        self.assertEqual(list_resp.status_code, 200)
        payload = list_resp.json()
        self.assertEqual({row["id"] for row in payload["orgs"]}, {str(org_a.id), str(org_b.id)})
        self.assertTrue(all(row["role"] == OrgMembership.Role.PM for row in payload["orgs"]))

    def test_platform_pm_can_manage_memberships_without_memberships(self) -> None:
        platform_pm = get_user_model().objects.create_user(
            email="pm@example.com",
            password="pw",
            is_staff=True,
        )
        target = get_user_model().objects.create_user(email="target@example.com", password="pw")

        org = Org.objects.create(name="Org")

        self.client.force_login(platform_pm)

        create_membership = self._post_json(
            f"/api/orgs/{org.id}/memberships",
            {"email": target.email, "role": OrgMembership.Role.MEMBER},
        )
        self.assertEqual(create_membership.status_code, 201)

        membership = OrgMembership.objects.get(org=org, user=target)

        patch_membership = self._patch_json(
            f"/api/orgs/{org.id}/memberships/{membership.id}",
            {"role": OrgMembership.Role.PM},
        )
        self.assertEqual(patch_membership.status_code, 200)

        membership.refresh_from_db()
        self.assertEqual(membership.role, OrgMembership.Role.PM)
        self.assertTrue(
            AuditEvent.objects.filter(org=org, event_type="org_membership.role_changed").exists()
        )

    def test_client_only_user_cannot_create_orgs(self) -> None:
        client_user = get_user_model().objects.create_user(
            email="client@example.com",
            password="pw",
        )
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=client_user, role=OrgMembership.Role.CLIENT)

        self.client.force_login(client_user)
        resp = self._post_json("/api/orgs", {"name": "Should fail"})
        self.assertEqual(resp.status_code, 403)

    def test_org_detail_update_delete_and_logo_permissions(self) -> None:
        admin = get_user_model().objects.create_user(email="admin@example.com", password="pw")
        pm = get_user_model().objects.create_user(email="pm@example.com", password="pw")
        member = get_user_model().objects.create_user(email="member@example.com", password="pw")
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=admin, role=OrgMembership.Role.ADMIN)
        OrgMembership.objects.create(org=org, user=pm, role=OrgMembership.Role.PM)
        OrgMembership.objects.create(org=org, user=member, role=OrgMembership.Role.MEMBER)

        client_member = self.client_class()
        client_member.force_login(member)
        patch_forbidden = self._patch_json(
            f"/api/orgs/{org.id}",
            {"name": "New name"},
            client=client_member,
        )
        self.assertEqual(patch_forbidden.status_code, 403)

        client_pm = self.client_class()
        client_pm.force_login(pm)
        patch_ok = self._patch_json(f"/api/orgs/{org.id}", {"name": "New name"}, client=client_pm)
        self.assertEqual(patch_ok.status_code, 200)
        org.refresh_from_db()
        self.assertEqual(org.name, "New name")

        delete_forbidden = client_pm.delete(f"/api/orgs/{org.id}")
        self.assertEqual(delete_forbidden.status_code, 403)

        logo_file = SimpleUploadedFile(
            "logo.png",
            b"\x89PNG\r\n\x1a\n" + b"0" * 1024,
            content_type="image/png",
        )
        upload_logo = client_pm.post(f"/api/orgs/{org.id}/logo", data={"file": logo_file})
        self.assertEqual(upload_logo.status_code, 200)
        self.assertIsNotNone(upload_logo.json()["org"]["logo_url"])

        clear_logo = client_pm.delete(f"/api/orgs/{org.id}/logo")
        self.assertEqual(clear_logo.status_code, 200)
        self.assertIsNone(clear_logo.json()["org"]["logo_url"])

        self.client.force_login(admin)
        delete_ok = self.client.delete(f"/api/orgs/{org.id}")
        self.assertEqual(delete_ok.status_code, 204)
        self.assertFalse(Org.objects.filter(id=org.id).exists())

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

        _key, minted = create_api_key(
            org=org, owner_user=pm, name="Automation", scopes=["read", "write"], created_by_user=pm
        )
        api_key_list = self.client.get(
            f"/api/orgs/{org.id}/memberships?role=client",
            HTTP_AUTHORIZATION=f"Bearer {minted.token}",
        )
        self.assertEqual(api_key_list.status_code, 403)

    def test_admin_can_create_org_membership_by_user_id_and_person_is_created(self) -> None:
        admin = get_user_model().objects.create_user(email="admin@example.com", password="pw")
        target = get_user_model().objects.create_user(
            email="target@example.com", password="pw", display_name="Target"
        )
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=admin, role=OrgMembership.Role.ADMIN)

        self.client.force_login(admin)
        response = self._post_json(
            f"/api/orgs/{org.id}/memberships",
            {"user_id": str(target.id), "role": OrgMembership.Role.MEMBER},
        )
        self.assertEqual(response.status_code, 201)

        membership = OrgMembership.objects.get(org=org, user=target)
        self.assertEqual(membership.role, OrgMembership.Role.MEMBER)

        person = Person.objects.get(org=org, user=target)
        self.assertEqual(person.email, target.email)
        self.assertEqual(person.preferred_name, "Target")

        event_types = set(AuditEvent.objects.filter(org=org).values_list("event_type", flat=True))
        self.assertIn("org_membership.created", event_types)

    def test_admin_can_create_org_membership_by_email_default_role(self) -> None:
        pm = get_user_model().objects.create_user(email="pm@example.com", password="pw")
        target = get_user_model().objects.create_user(email="target@example.com", password="pw")
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=pm, role=OrgMembership.Role.PM)

        self.client.force_login(pm)
        response = self._post_json(
            f"/api/orgs/{org.id}/memberships",
            {"email": target.email},
        )
        self.assertEqual(response.status_code, 201)
        membership = OrgMembership.objects.get(org=org, user=target)
        self.assertEqual(membership.role, OrgMembership.Role.MEMBER)

        again = self._post_json(f"/api/orgs/{org.id}/memberships", {"email": target.email})
        self.assertEqual(again.status_code, 409)

    def test_org_memberships_create_rejects_bad_payload_and_forbids_non_admin_pm(self) -> None:
        pm = get_user_model().objects.create_user(email="pm@example.com", password="pw")
        member = get_user_model().objects.create_user(email="member@example.com", password="pw")
        target = get_user_model().objects.create_user(email="target@example.com", password="pw")
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=pm, role=OrgMembership.Role.PM)
        OrgMembership.objects.create(org=org, user=member, role=OrgMembership.Role.MEMBER)

        # Must provide exactly one of user_id/email.
        self.client.force_login(pm)
        both = self._post_json(
            f"/api/orgs/{org.id}/memberships",
            {"user_id": str(target.id), "email": target.email},
        )
        self.assertEqual(both.status_code, 400)

        missing = self._post_json(f"/api/orgs/{org.id}/memberships", {})
        self.assertEqual(missing.status_code, 400)

        # Member is forbidden.
        member_client = self.client_class()
        member_client.force_login(member)
        forbidden = self._post_json(
            f"/api/orgs/{org.id}/memberships",
            {"email": target.email},
            client=member_client,
        )
        self.assertEqual(forbidden.status_code, 403)

        # API keys are forbidden.
        _key, minted = create_api_key(
            org=org, owner_user=pm, name="Automation", scopes=["read", "write"], created_by_user=pm
        )
        api_key_request = self.client.post(
            f"/api/orgs/{org.id}/memberships",
            data=json.dumps({"email": target.email}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {minted.token}",
        )
        self.assertEqual(api_key_request.status_code, 403)

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

    def test_admin_cannot_update_person_to_duplicate_email(self) -> None:
        admin = get_user_model().objects.create_user(email="admin@example.com", password="pw")
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=admin, role=OrgMembership.Role.ADMIN)

        self.client.force_login(admin)

        alice_resp = self._post_json(
            f"/api/orgs/{org.id}/people",
            {
                "full_name": "Alice Example",
                "email": "alice@example.com",
                "timezone": "America/New_York",
            },
        )
        self.assertEqual(alice_resp.status_code, 200)

        bob_resp = self._post_json(
            f"/api/orgs/{org.id}/people",
            {
                "full_name": "Bob Example",
                "email": "bob@example.com",
                "timezone": "America/New_York",
            },
        )
        self.assertEqual(bob_resp.status_code, 200)
        bob_id = bob_resp.json()["person"]["id"]

        patch_resp = self._patch_json(
            f"/api/orgs/{org.id}/people/{bob_id}",
            {"email": "alice@example.com"},
        )
        self.assertEqual(patch_resp.status_code, 400)
        self.assertEqual(patch_resp.json()["error"], "person already exists")

    def test_person_project_memberships_are_listed_for_active_people_only(self) -> None:
        admin = get_user_model().objects.create_user(email="admin@example.com", password="pw")
        member_user = get_user_model().objects.create_user(
            email="member@example.com", password="pw"
        )
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=admin, role=OrgMembership.Role.ADMIN)
        OrgMembership.objects.create(org=org, user=member_user, role=OrgMembership.Role.MEMBER)

        project_a = Project.objects.create(org=org, name="Alpha")
        project_b = Project.objects.create(org=org, name="Beta")

        active_person = Person.objects.create(org=org, user=member_user, full_name="Member")
        candidate_person = Person.objects.create(org=org, full_name="Candidate")

        ProjectMembership.objects.create(project=project_b, user=member_user)
        ProjectMembership.objects.create(project=project_a, user=member_user)

        member_client = self.client_class()
        member_client.force_login(member_user)
        forbidden = member_client.get(
            f"/api/orgs/{org.id}/people/{active_person.id}/project-memberships"
        )
        self.assertEqual(forbidden.status_code, 403)

        self.client.force_login(admin)

        candidate_resp = self.client.get(
            f"/api/orgs/{org.id}/people/{candidate_person.id}/project-memberships"
        )
        self.assertEqual(candidate_resp.status_code, 200)
        self.assertEqual(candidate_resp.json()["memberships"], [])

        active_resp = self.client.get(
            f"/api/orgs/{org.id}/people/{active_person.id}/project-memberships"
        )
        self.assertEqual(active_resp.status_code, 200)
        memberships = active_resp.json()["memberships"]

        self.assertEqual([m["project"]["name"] for m in memberships], ["Alpha", "Beta"])

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

    def test_admin_can_manage_person_availability_schedule_weekly_and_exceptions(self) -> None:
        admin = get_user_model().objects.create_user(email="admin@example.com", password="pw")
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=admin, role=OrgMembership.Role.ADMIN)

        person = Person.objects.create(
            org=org, full_name="Alice", email="alice@example.com", timezone="UTC"
        )

        self.client.force_login(admin)

        create_window = self._post_json(
            f"/api/orgs/{org.id}/people/{person.id}/availability/weekly-windows",
            {"weekday": 0, "start_time": "09:00", "end_time": "12:00"},
        )
        self.assertEqual(create_window.status_code, 200)
        weekly_window_id = create_window.json()["weekly_window"]["id"]

        schedule = self.client.get(
            f"/api/orgs/{org.id}/people/{person.id}/availability?start_at=2026-02-16T00:00:00Z&end_at=2026-02-17T00:00:00Z"
        )
        self.assertEqual(schedule.status_code, 200)
        payload = schedule.json()
        self.assertEqual(payload["timezone"], "UTC")
        self.assertEqual(len(payload["weekly_windows"]), 1)
        self.assertEqual(payload["weekly_windows"][0]["weekday"], 0)
        self.assertEqual(payload["weekly_windows"][0]["start_time"], "09:00")
        self.assertEqual(payload["weekly_windows"][0]["end_time"], "12:00")
        self.assertEqual(payload["summary"]["has_availability"], True)
        self.assertEqual(payload["summary"]["minutes_available"], 180)
        self.assertEqual(payload["summary"]["next_available_at"], "2026-02-16T09:00:00Z")

        create_exc = self._post_json(
            f"/api/orgs/{org.id}/people/{person.id}/availability/exceptions",
            {
                "kind": "time_off",
                "starts_at": "2026-02-16T10:00:00Z",
                "ends_at": "2026-02-16T11:00:00Z",
                "title": "Doctor",
                "notes": "Out for an appointment",
            },
        )
        self.assertEqual(create_exc.status_code, 200)

        schedule2 = self.client.get(
            f"/api/orgs/{org.id}/people/{person.id}/availability?start_at=2026-02-16T00:00:00Z&end_at=2026-02-17T00:00:00Z"
        )
        self.assertEqual(schedule2.status_code, 200)
        payload2 = schedule2.json()
        self.assertEqual(payload2["summary"]["minutes_available"], 120)

        patch_window = self._patch_json(
            f"/api/orgs/{org.id}/people/{person.id}/availability/weekly-windows/{weekly_window_id}",
            {"end_time": "13:00"},
        )
        self.assertEqual(patch_window.status_code, 200)

        schedule3 = self.client.get(
            f"/api/orgs/{org.id}/people/{person.id}/availability?start_at=2026-02-16T00:00:00Z&end_at=2026-02-17T00:00:00Z"
        )
        self.assertEqual(schedule3.status_code, 200)
        payload3 = schedule3.json()
        self.assertEqual(payload3["summary"]["minutes_available"], 180)

    def test_member_can_view_own_person_availability_schedule(self) -> None:
        user = get_user_model().objects.create_user(email="member@example.com", password="pw")
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=user, role=OrgMembership.Role.MEMBER)

        person = Person.objects.create(
            org=org,
            user=user,
            full_name="Member",
            email="member@example.com",
            timezone="UTC",
        )

        self.client.force_login(user)

        schedule = self.client.get(
            f"/api/orgs/{org.id}/people/{person.id}/availability?start_at=2026-02-16T00:00:00Z&end_at=2026-02-17T00:00:00Z"
        )
        self.assertEqual(schedule.status_code, 200)

        other_user = get_user_model().objects.create_user(email="other@example.com", password="pw")
        OrgMembership.objects.create(org=org, user=other_user, role=OrgMembership.Role.MEMBER)
        other_person = Person.objects.create(
            org=org,
            user=other_user,
            full_name="Other",
            email="other@example.com",
            timezone="UTC",
        )

        forbidden = self.client.get(
            f"/api/orgs/{org.id}/people/{other_person.id}/availability?start_at=2026-02-16T00:00:00Z&end_at=2026-02-17T00:00:00Z"
        )
        self.assertEqual(forbidden.status_code, 403)

    def test_admin_can_search_people_availability(self) -> None:
        admin = get_user_model().objects.create_user(email="admin@example.com", password="pw")
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=admin, role=OrgMembership.Role.ADMIN)

        person = Person.objects.create(
            org=org, full_name="Alice", email="alice@example.com", timezone="UTC"
        )

        self.client.force_login(admin)

        self._post_json(
            f"/api/orgs/{org.id}/people/{person.id}/availability/weekly-windows",
            {"weekday": 0, "start_time": "09:00", "end_time": "12:00"},
        )

        search = self.client.get(
            f"/api/orgs/{org.id}/people/availability-search?start_at=2026-02-16T00:00:00Z&end_at=2026-02-17T00:00:00Z"
        )
        self.assertEqual(search.status_code, 200)
        data = search.json()
        self.assertEqual(data["start_at"], "2026-02-16T00:00:00+00:00")
        self.assertEqual(data["end_at"], "2026-02-17T00:00:00+00:00")
        matches = data["matches"]
        self.assertTrue(any(row["person_id"] == str(person.id) for row in matches))

    def test_admin_can_manage_person_contact_entries(self) -> None:
        admin = get_user_model().objects.create_user(email="admin@example.com", password="pw")
        member = get_user_model().objects.create_user(email="member@example.com", password="pw")
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=admin, role=OrgMembership.Role.ADMIN)
        OrgMembership.objects.create(org=org, user=member, role=OrgMembership.Role.MEMBER)

        person = Person.objects.create(org=org, full_name="Candidate")

        self.client.force_login(admin)

        create_resp = self._post_json(
            f"/api/orgs/{org.id}/people/{person.id}/contact-entries",
            {
                "kind": "call",
                "occurred_at": "2026-02-20T12:00:00Z",
                "summary": "Intro call",
                "notes": "Discussed availability",
            },
        )
        self.assertEqual(create_resp.status_code, 200)
        entry = create_resp.json()["entry"]
        entry_id = entry["id"]
        self.assertEqual(entry["kind"], "call")
        self.assertEqual(entry["summary"], "Intro call")

        list_resp = self.client.get(f"/api/orgs/{org.id}/people/{person.id}/contact-entries")
        self.assertEqual(list_resp.status_code, 200)
        self.assertEqual(len(list_resp.json()["entries"]), 1)

        patch_resp = self._patch_json(
            f"/api/orgs/{org.id}/people/{person.id}/contact-entries/{entry_id}",
            {"summary": "Updated summary"},
        )
        self.assertEqual(patch_resp.status_code, 200)
        self.assertEqual(patch_resp.json()["entry"]["summary"], "Updated summary")

        delete_resp = self.client.delete(
            f"/api/orgs/{org.id}/people/{person.id}/contact-entries/{entry_id}"
        )
        self.assertEqual(delete_resp.status_code, 204)

        list_resp2 = self.client.get(f"/api/orgs/{org.id}/people/{person.id}/contact-entries")
        self.assertEqual(list_resp2.status_code, 200)
        self.assertEqual(list_resp2.json()["entries"], [])

        member_client = self.client_class()
        member_client.force_login(member)
        forbidden = member_client.get(f"/api/orgs/{org.id}/people/{person.id}/contact-entries")
        self.assertEqual(forbidden.status_code, 403)

    def test_admin_can_manage_person_message_threads_and_messages(self) -> None:
        admin = get_user_model().objects.create_user(email="admin@example.com", password="pw")
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=admin, role=OrgMembership.Role.ADMIN)

        person = Person.objects.create(org=org, full_name="Candidate")

        self.client.force_login(admin)

        thread_resp = self._post_json(
            f"/api/orgs/{org.id}/people/{person.id}/message-threads",
            {"title": "Onboarding"},
        )
        self.assertEqual(thread_resp.status_code, 200)
        thread_id = thread_resp.json()["thread"]["id"]

        msg_resp = self._post_json(
            f"/api/orgs/{org.id}/people/{person.id}/message-threads/{thread_id}/messages",
            {"body_markdown": "Hello <script>alert(1)</script>"},
        )
        self.assertEqual(msg_resp.status_code, 200)
        msg = msg_resp.json()["message"]
        self.assertIn("<p>", msg["body_html"])
        self.assertNotIn("<script", msg["body_html"].lower())

        list_msgs = self.client.get(
            f"/api/orgs/{org.id}/people/{person.id}/message-threads/{thread_id}/messages"
        )
        self.assertEqual(list_msgs.status_code, 200)
        self.assertEqual(len(list_msgs.json()["messages"]), 1)

        patch_thread = self._patch_json(
            f"/api/orgs/{org.id}/people/{person.id}/message-threads/{thread_id}",
            {"title": "Onboarding v2"},
        )
        self.assertEqual(patch_thread.status_code, 200)
        self.assertEqual(patch_thread.json()["thread"]["title"], "Onboarding v2")

        delete_thread = self.client.delete(
            f"/api/orgs/{org.id}/people/{person.id}/message-threads/{thread_id}"
        )
        self.assertEqual(delete_thread.status_code, 204)

    def test_admin_can_manage_person_rates_and_payments(self) -> None:
        admin = get_user_model().objects.create_user(email="admin@example.com", password="pw")
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=admin, role=OrgMembership.Role.ADMIN)

        person = Person.objects.create(org=org, full_name="Candidate")

        self.client.force_login(admin)

        rate_resp = self._post_json(
            f"/api/orgs/{org.id}/people/{person.id}/rates",
            {"currency": "USD", "amount_cents": 10000, "effective_date": "2026-02-20"},
        )
        self.assertEqual(rate_resp.status_code, 200)
        rate_id = rate_resp.json()["rate"]["id"]

        rates_list = self.client.get(f"/api/orgs/{org.id}/people/{person.id}/rates")
        self.assertEqual(rates_list.status_code, 200)
        self.assertEqual(len(rates_list.json()["rates"]), 1)

        patch_rate = self._patch_json(
            f"/api/orgs/{org.id}/people/{person.id}/rates/{rate_id}",
            {"notes": "Hourly"},
        )
        self.assertEqual(patch_rate.status_code, 200)
        self.assertEqual(patch_rate.json()["rate"]["notes"], "Hourly")

        del_rate = self.client.delete(f"/api/orgs/{org.id}/people/{person.id}/rates/{rate_id}")
        self.assertEqual(del_rate.status_code, 204)

        payment_resp = self._post_json(
            f"/api/orgs/{org.id}/people/{person.id}/payments",
            {"currency": "USD", "amount_cents": 5000, "paid_date": "2026-02-21"},
        )
        self.assertEqual(payment_resp.status_code, 200)
        payment_id = payment_resp.json()["payment"]["id"]

        payments_list = self.client.get(f"/api/orgs/{org.id}/people/{person.id}/payments")
        self.assertEqual(payments_list.status_code, 200)
        self.assertEqual(len(payments_list.json()["payments"]), 1)

        patch_payment = self._patch_json(
            f"/api/orgs/{org.id}/people/{person.id}/payments/{payment_id}",
            {"notes": "Invoice 001"},
        )
        self.assertEqual(patch_payment.status_code, 200)
        self.assertEqual(patch_payment.json()["payment"]["notes"], "Invoice 001")

        del_payment = self.client.delete(
            f"/api/orgs/{org.id}/people/{person.id}/payments/{payment_id}"
        )
        self.assertEqual(del_payment.status_code, 204)

    def test_member_can_self_update_person_profile(self) -> None:
        user = get_user_model().objects.create_user(email="member@example.com", password="pw")
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=user, role=OrgMembership.Role.MEMBER)

        self.client.force_login(user)

        get_me = self.client.get(f"/api/orgs/{org.id}/people/me")
        self.assertEqual(get_me.status_code, 200)
        person_id = get_me.json()["person"]["id"]
        self.assertEqual(get_me.json()["person"]["status"], "active")

        patch_me = self._patch_json(
            f"/api/orgs/{org.id}/people/me",
            {"preferred_name": "Member", "timezone": "America/New_York", "skills": ["python"]},
        )
        self.assertEqual(patch_me.status_code, 200)
        payload = patch_me.json()["person"]
        self.assertEqual(payload["preferred_name"], "Member")
        self.assertEqual(payload["timezone"], "America/New_York")
        self.assertEqual(payload["skills"], ["python"])

        person = Person.objects.get(id=person_id)
        self.assertEqual(person.user_id, user.id)
