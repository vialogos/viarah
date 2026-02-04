import json

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase

from identity.models import Org, OrgMembership
from work_items.models import Epic, Project, Task

from .models import EmailDeliveryLog, InAppNotification, NotificationEventType
from .services import emit_assignment_changed, emit_project_event


class NotificationsApiTests(TestCase):
    def _post_json(self, url: str, payload: dict, *, client=None):
        active_client = client or self.client
        return active_client.post(url, data=json.dumps(payload), content_type="application/json")

    def _patch_json(self, url: str, payload: dict, *, client=None):
        active_client = client or self.client
        return active_client.patch(url, data=json.dumps(payload), content_type="application/json")

    def test_inbox_and_badge_are_user_scoped(self) -> None:
        user_a = get_user_model().objects.create_user(email="a@example.com", password="pw")
        user_b = get_user_model().objects.create_user(email="b@example.com", password="pw")
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=user_a, role=OrgMembership.Role.MEMBER)
        OrgMembership.objects.create(org=org, user=user_b, role=OrgMembership.Role.MEMBER)
        project = Project.objects.create(org=org, name="P")
        epic = Epic.objects.create(project=project, title="E")
        task = Task.objects.create(epic=epic, title="T")

        emit_project_event(
            org=org,
            project=project,
            event_type=NotificationEventType.STATUS_CHANGED,
            actor_user=user_a,
            data={"work_item_type": "task", "work_item_id": str(task.id)},
            client_visible=False,
        )

        self.client.force_login(user_b)
        badge = self.client.get(f"/api/orgs/{org.id}/me/notifications/badge")
        self.assertEqual(badge.status_code, 200)
        self.assertEqual(badge.json()["unread_count"], 1)

        inbox = self.client.get(f"/api/orgs/{org.id}/me/notifications")
        self.assertEqual(inbox.status_code, 200)
        self.assertEqual(len(inbox.json()["notifications"]), 1)

        # A should not see the notification they acted on (actor excluded).
        self.client.force_login(user_a)
        badge_a = self.client.get(f"/api/orgs/{org.id}/me/notifications/badge")
        self.assertEqual(badge_a.status_code, 200)
        self.assertEqual(badge_a.json()["unread_count"], 0)

    def test_mark_read_is_idempotent(self) -> None:
        user_a = get_user_model().objects.create_user(email="a@example.com", password="pw")
        user_b = get_user_model().objects.create_user(email="b@example.com", password="pw")
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=user_a, role=OrgMembership.Role.MEMBER)
        OrgMembership.objects.create(org=org, user=user_b, role=OrgMembership.Role.MEMBER)
        project = Project.objects.create(org=org, name="P")
        epic = Epic.objects.create(project=project, title="E")
        task = Task.objects.create(epic=epic, title="T")

        emit_project_event(
            org=org,
            project=project,
            event_type=NotificationEventType.STATUS_CHANGED,
            actor_user=user_a,
            data={"work_item_type": "task", "work_item_id": str(task.id)},
            client_visible=False,
        )

        self.client.force_login(user_b)
        inbox = self.client.get(f"/api/orgs/{org.id}/me/notifications?limit=1")
        notification_id = inbox.json()["notifications"][0]["id"]

        res1 = self._patch_json(
            f"/api/orgs/{org.id}/me/notifications/{notification_id}",
            {"read": True},
        )
        self.assertEqual(res1.status_code, 200)

        res2 = self._patch_json(
            f"/api/orgs/{org.id}/me/notifications/{notification_id}",
            {"read": True},
        )
        self.assertEqual(res2.status_code, 200)

        badge = self.client.get(f"/api/orgs/{org.id}/me/notifications/badge")
        self.assertEqual(badge.json()["unread_count"], 0)

    def test_assignment_changed_creates_email_delivery_log(self) -> None:
        actor = get_user_model().objects.create_user(email="actor@example.com", password="pw")
        assignee = get_user_model().objects.create_user(email="assignee@example.com", password="pw")
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=actor, role=OrgMembership.Role.PM)
        OrgMembership.objects.create(org=org, user=assignee, role=OrgMembership.Role.MEMBER)
        project = Project.objects.create(org=org, name="P")
        epic = Epic.objects.create(project=project, title="E")
        task = Task.objects.create(epic=epic, title="T")

        emit_assignment_changed(
            org=org,
            project=project,
            actor_user=actor,
            task_id=str(task.id),
            old_assignee_user_id=None,
            new_assignee_user_id=str(assignee.id),
        )

        self.assertEqual(InAppNotification.objects.count(), 1)
        self.assertEqual(EmailDeliveryLog.objects.count(), 1)

        # Task execution uses Django's test email backend; no SMTP needed.
        log = EmailDeliveryLog.objects.first()
        self.assertEqual(log.status, "queued")
        from .tasks import send_email_delivery

        send_email_delivery(str(log.id))
        log.refresh_from_db()
        self.assertEqual(log.status, "success")
        self.assertEqual(len(mail.outbox), 1)
