from __future__ import annotations

import logging
import uuid

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

logger = logging.getLogger(__name__)


class OrgEventsConsumer(AsyncJsonWebsocketConsumer):
    """Read-only realtime event stream scoped to a single org.

    Why this exists:
    - Session auth means cookies would otherwise allow cross-site websocket access.
      We rely on `AllowedHostsOriginValidator` (in ASGI routing) plus an explicit
      org membership check here.
    - Events are IDs-only; clients refetch authoritative objects over REST.
    """

    org_group_name: str | None = None

    async def connect(self) -> None:
        user = self.scope.get("user")
        if user is None or not getattr(user, "is_authenticated", False):
            await self.close(code=4401)
            return

        raw_org_id = self.scope.get("url_route", {}).get("kwargs", {}).get("org_id")
        try:
            org_id = uuid.UUID(str(raw_org_id))
        except (TypeError, ValueError):
            await self.close(code=4400)
            return

        allowed = await self._user_can_connect(user_id=user.id, org_id=org_id)
        if not allowed:
            await self.close(code=4403)
            return

        if self.channel_layer is None:
            await self.close(code=1011)
            return

        self.org_group_name = f"org.{org_id}"
        try:
            await self.channel_layer.group_add(self.org_group_name, self.channel_name)
        except Exception:
            logger.exception("realtime group_add failed", extra={"org_id": str(org_id)})
            await self.close(code=1011)
            return

        await self.accept()

    async def disconnect(self, close_code: int) -> None:
        if self.channel_layer is None or not self.org_group_name:
            return
        try:
            await self.channel_layer.group_discard(self.org_group_name, self.channel_name)
        except Exception:
            logger.exception(
                "realtime group_discard failed",
                extra={"org_group_name": self.org_group_name, "close_code": close_code},
            )

    async def receive_json(self, content: dict, **kwargs) -> None:  # noqa: ARG002
        # v1 is server-push only (no client messages expected).
        return

    async def org_event(self, event: dict) -> None:
        payload = event.get("event")
        if payload is None:
            return
        await self.send_json(payload)

    @database_sync_to_async
    def _user_can_connect(self, *, user_id: uuid.UUID, org_id: uuid.UUID) -> bool:
        from identity.models import OrgMembership

        return OrgMembership.objects.filter(
            user_id=user_id,
            org_id=org_id,
            role__in={
                OrgMembership.Role.ADMIN,
                OrgMembership.Role.PM,
                OrgMembership.Role.MEMBER,
            },
        ).exists()
