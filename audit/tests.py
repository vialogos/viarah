from django.contrib.auth import get_user_model
from django.test import TestCase

from identity.models import Org, OrgMembership

from .services import write_audit_event


class AuditEventsApiTests(TestCase):
    def test_list_audit_events_includes_actor_user_when_available(self) -> None:
        pm = get_user_model().objects.create_user(
            email="pm@example.com", password="pw", display_name="PM"
        )
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=pm, role=OrgMembership.Role.PM)
        write_audit_event(org=org, actor_user=pm, event_type="workflow.created", metadata={})

        self.client.force_login(pm)
        resp = self.client.get(f"/api/orgs/{org.id}/audit-events")
        self.assertEqual(resp.status_code, 200)

        events = resp.json()["events"]
        self.assertGreaterEqual(len(events), 1)

        event = events[0]
        self.assertEqual(event["actor_user_id"], str(pm.id))
        self.assertEqual(
            event["actor_user"],
            {"id": str(pm.id), "email": pm.email, "display_name": "PM"},
        )

    def test_list_audit_events_requires_pm_or_admin(self) -> None:
        member = get_user_model().objects.create_user(email="member@example.com", password="pw")
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=member, role=OrgMembership.Role.MEMBER)

        self.client.force_login(member)
        resp = self.client.get(f"/api/orgs/{org.id}/audit-events")
        self.assertEqual(resp.status_code, 403)
