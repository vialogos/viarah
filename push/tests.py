from __future__ import annotations

import json
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings

from identity.models import Org, OrgMembership
from notifications.models import NotificationChannel, NotificationEventType, NotificationPreference
from notifications.services import emit_project_event
from work_items.models import Project

from .models import PushSubscription
from .views import subscriptions_collection_view, vapid_public_key_view


class PushApiTests(TestCase):
    def _post_json(self, url: str, payload: dict, *, client=None):
        active_client = client or self.client
        return active_client.post(url, data=json.dumps(payload), content_type="application/json")

    def test_vapid_public_key_requires_session_auth(self) -> None:
        res = self.client.get("/api/push/vapid_public_key")
        self.assertEqual(res.status_code, 401)

    @override_settings(WEBPUSH_VAPID_PUBLIC_KEY="pk")
    def test_vapid_public_key_returns_503_when_not_fully_configured(self) -> None:
        user = get_user_model().objects.create_user(email="a@example.com", password="pw")
        self.client.force_login(user)
        res = self.client.get("/api/push/vapid_public_key")
        self.assertEqual(res.status_code, 503)

    @override_settings(
        WEBPUSH_VAPID_PUBLIC_KEY="pk",
        WEBPUSH_VAPID_PRIVATE_KEY="sk",
        WEBPUSH_VAPID_SUBJECT="mailto:test@example.com",
    )
    def test_vapid_public_key_returns_key(self) -> None:
        user = get_user_model().objects.create_user(email="a@example.com", password="pw")
        self.client.force_login(user)
        res = self.client.get("/api/push/vapid_public_key")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["public_key"], "pk")

    def test_vapid_public_key_forbids_api_key_principal(self) -> None:
        user = get_user_model().objects.create_user(email="a@example.com", password="pw")
        req = RequestFactory().get("/api/push/vapid_public_key")
        req.user = user
        req.api_key_principal = object()
        res = vapid_public_key_view(req)
        self.assertEqual(res.status_code, 403)

    def test_subscribe_upserts_and_redacts_keys(self) -> None:
        user = get_user_model().objects.create_user(email="a@example.com", password="pw")
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=user, role=OrgMembership.Role.MEMBER)
        Project.objects.create(org=org, name="P")

        self.client.force_login(user)
        payload = {
            "subscription": {
                "endpoint": "https://example.com/endpoint",
                "keys": {"p256dh": "pkey", "auth": "akey"},
                "expirationTime": None,
            },
            "user_agent": "UA",
        }
        res = self._post_json("/api/push/subscriptions", payload)
        self.assertEqual(res.status_code, 201)
        body = res.json()["subscription"]
        self.assertIn("id", body)
        self.assertEqual(body["endpoint"], payload["subscription"]["endpoint"])
        self.assertNotIn("p256dh", body)
        self.assertNotIn("auth", body)

        self.assertEqual(PushSubscription.objects.count(), 1)
        row = PushSubscription.objects.first()
        self.assertEqual(row.user_id, user.id)
        self.assertEqual(row.p256dh, "pkey")
        self.assertEqual(row.auth, "akey")

    def test_subscribe_initializes_push_prefs_for_comment_and_report(self) -> None:
        user = get_user_model().objects.create_user(email="a@example.com", password="pw")
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=user, role=OrgMembership.Role.MEMBER)
        project = Project.objects.create(org=org, name="P")

        # Explicit disable should not be overridden.
        NotificationPreference.objects.create(
            org=org,
            project=project,
            user=user,
            event_type=NotificationEventType.COMMENT_CREATED,
            channel=NotificationChannel.PUSH,
            enabled=False,
        )

        self.client.force_login(user)
        payload = {
            "subscription": {
                "endpoint": "https://example.com/endpoint",
                "keys": {"p256dh": "pkey", "auth": "akey"},
                "expirationTime": None,
            },
            "user_agent": "UA",
        }
        res = self._post_json("/api/push/subscriptions", payload)
        self.assertEqual(res.status_code, 201)

        # comment remains disabled; report gets enabled.
        comment_pref = NotificationPreference.objects.get(
            user=user,
            project=project,
            event_type=NotificationEventType.COMMENT_CREATED,
            channel=NotificationChannel.PUSH,
        )
        self.assertFalse(comment_pref.enabled)
        report_pref = NotificationPreference.objects.get(
            user=user,
            project=project,
            event_type=NotificationEventType.REPORT_PUBLISHED,
            channel=NotificationChannel.PUSH,
        )
        self.assertTrue(report_pref.enabled)

    @override_settings(
        WEBPUSH_VAPID_PUBLIC_KEY="pk",
        WEBPUSH_VAPID_PRIVATE_KEY="sk",
        WEBPUSH_VAPID_SUBJECT="mailto:test@example.com",
    )
    def test_emit_project_event_enqueues_push_for_enabled_users(self) -> None:
        actor = get_user_model().objects.create_user(email="actor@example.com", password="pw")
        recipient = get_user_model().objects.create_user(email="b@example.com", password="pw")
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=actor, role=OrgMembership.Role.MEMBER)
        OrgMembership.objects.create(org=org, user=recipient, role=OrgMembership.Role.MEMBER)
        project = Project.objects.create(org=org, name="P")

        NotificationPreference.objects.create(
            org=org,
            project=project,
            user=recipient,
            event_type=NotificationEventType.COMMENT_CREATED,
            channel=NotificationChannel.PUSH,
            enabled=True,
        )

        with mock.patch("push.tasks.send_push_for_notification_event.delay") as delay:
            with self.captureOnCommitCallbacks(execute=True):
                emit_project_event(
                    org=org,
                    project=project,
                    event_type=NotificationEventType.COMMENT_CREATED,
                    actor_user=actor,
                    data={"work_item_type": "task", "work_item_id": "t", "comment_id": "c"},
                    client_visible=False,
                )
            self.assertEqual(delay.call_count, 1)

    def test_subscriptions_collection_forbids_api_key_principal(self) -> None:
        user = get_user_model().objects.create_user(email="a@example.com", password="pw")
        req = RequestFactory().get("/api/push/subscriptions")
        req.user = user
        req.api_key_principal = object()
        res = subscriptions_collection_view(req)
        self.assertEqual(res.status_code, 403)
