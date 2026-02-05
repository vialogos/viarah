from __future__ import annotations

import getpass
import json
import os
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from api_keys.models import ApiKey
from api_keys.services import create_api_key
from identity.models import Org, OrgMembership
from work_items.models import Project


def _require_cleaned(value: str, *, flag: str) -> str:
    cleaned = str(value or "").strip()
    if not cleaned:
        raise CommandError(f"{flag} is required")
    return cleaned


def _split_scopes(scopes: list[str] | None) -> list[str] | None:
    if scopes is None:
        return None

    flattened: list[str] = []
    for raw in scopes:
        for part in str(raw).split(","):
            cleaned = part.strip()
            if cleaned:
                flattened.append(cleaned)
    return flattened


def _write_token_file(*, path: Path, payload: dict) -> None:
    path = path.expanduser().resolve()
    if path.exists():
        raise CommandError("--write-token-file target already exists")

    path.parent.mkdir(parents=True, exist_ok=True)

    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(str(path), flags, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload))
            handle.write("\n")
        os.chmod(path, 0o600)
    except Exception:
        try:
            os.unlink(path)
        except OSError:
            pass
        raise


class Command(BaseCommand):
    """Bootstrap a fresh ViaRah install into a usable state (v1).

    Creates or reuses:
    - Org
    - PM user + org membership (role `pm` by default)
    - Project
    - API key (project-restricted by default; org-scoped optional)

    Security:
    - Passwords are never printed.
    - API key tokens are never printed unless `--reveal` is explicitly set.
    - Tokens can optionally be written to a file created with mode `0600`.

    Idempotency:
    - Safe to re-run with identical inputs; will reuse existing rows and avoid duplicates.
    - Ambiguous name matches (multiple rows) cause a hard error and no writes.
    """

    help = "Bootstrap a fresh ViaRah install (first org + PM + project + API key)."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--org-name",
            required=True,
            help="Organization name (must be unambiguous)",
        )

        parser.add_argument("--pm-email", required=True, help="PM user email (login)")
        parser.add_argument(
            "--pm-display-name",
            default="",
            help="PM display name (only set when creating a new user)",
        )
        parser.add_argument(
            "--pm-role",
            default=OrgMembership.Role.PM,
            choices=[OrgMembership.Role.PM, OrgMembership.Role.ADMIN],
            help="Org role to grant the PM user (default: pm)",
        )
        parser.add_argument(
            "--pm-password",
            default="",
            help=(
                "Password to set when creating a new user. "
                "Prefer the interactive prompt; CLI args can leak via shell history."
            ),
        )

        parser.add_argument(
            "--project-name",
            required=True,
            help="Project name (must be unambiguous within org)",
        )
        parser.add_argument(
            "--project-description",
            default="",
            help="Project description (create-only)",
        )

        parser.add_argument(
            "--api-key-name",
            required=True,
            help="API key name (must be unambiguous)",
        )
        parser.add_argument(
            "--api-scopes",
            nargs="*",
            default=None,
            help=(
                "API key scopes (default: read). Values: read, write. "
                "Accepts comma-separated values."
            ),
        )
        parser.add_argument(
            "--org-scoped",
            action="store_true",
            help="Create the API key as org-scoped (not restricted to the project).",
        )
        parser.add_argument(
            "--reveal",
            action="store_true",
            help="Print the one-time API key token to stdout (sensitive).",
        )
        parser.add_argument(
            "--write-token-file",
            default="",
            help=(
                "Write the one-time API key token to a file created with mode 0600 "
                "(token is not printed)."
            ),
        )

    def handle(self, *args, **options) -> None:
        org_name = _require_cleaned(options.get("org_name"), flag="--org-name")

        pm_email = _require_cleaned(options.get("pm_email"), flag="--pm-email").lower()
        pm_display_name = str(options.get("pm_display_name") or "").strip()
        pm_role = str(options.get("pm_role") or "").strip()

        project_name = _require_cleaned(options.get("project_name"), flag="--project-name")
        project_description = str(options.get("project_description") or "").strip()

        api_key_name = _require_cleaned(options.get("api_key_name"), flag="--api-key-name")
        api_scopes = _split_scopes(options.get("api_scopes"))
        org_scoped = bool(options.get("org_scoped"))

        reveal = bool(options.get("reveal"))
        token_file_raw = str(options.get("write_token_file") or "").strip()
        token_file_path = Path(token_file_raw) if token_file_raw else None

        if pm_role not in OrgMembership.Role.values:
            raise CommandError("--pm-role must be one of: pm, admin")

        summary: dict = {"command": "bootstrap_v1", "warnings": []}
        minted_token = None
        token_written_to = None

        with transaction.atomic():
            org_qs = Org.objects.filter(name=org_name).order_by("created_at")
            if org_qs.count() > 1:
                raise CommandError("ambiguous org name match; multiple orgs exist with this name")

            org = org_qs.first()
            if org is None:
                org = Org.objects.create(name=org_name)
                summary["org"] = {"action": "created", "id": str(org.id), "name": org.name}
            else:
                summary["org"] = {"action": "reused", "id": str(org.id), "name": org.name}

            user_model = get_user_model()
            pm_user = user_model.objects.filter(email=pm_email).first()
            if pm_user is None:
                password = str(options.get("pm_password") or "")
                if not password:
                    password = getpass.getpass("PM user password (input hidden): ")
                if not password:
                    raise CommandError("password is required to create a new user")

                pm_user = user_model.objects.create_user(
                    email=pm_email,
                    password=password,
                    display_name=pm_display_name,
                )
                summary["pm_user"] = {
                    "action": "created",
                    "id": str(pm_user.id),
                    "email": pm_user.email,
                }
            else:
                summary["pm_user"] = {
                    "action": "reused",
                    "id": str(pm_user.id),
                    "email": pm_user.email,
                }

            membership, membership_created = OrgMembership.objects.get_or_create(
                org=org,
                user=pm_user,
                defaults={"role": pm_role},
            )
            membership_action = "created" if membership_created else "reused"
            if not membership_created and membership.role != pm_role:
                membership.role = pm_role
                membership.save(update_fields=["role"])
                membership_action = "updated"
            summary["membership"] = {
                "action": membership_action,
                "id": str(membership.id),
                "role": membership.role,
            }

            project_qs = Project.objects.filter(org=org, name=project_name).order_by("created_at")
            if project_qs.count() > 1:
                raise CommandError(
                    "ambiguous project name match; multiple projects exist in this org with this "
                    "name"
                )

            project = project_qs.first()
            if project is None:
                project = Project.objects.create(
                    org=org,
                    name=project_name,
                    description=project_description,
                )
                summary["project"] = {
                    "action": "created",
                    "id": str(project.id),
                    "name": project.name,
                }
            else:
                summary["project"] = {
                    "action": "reused",
                    "id": str(project.id),
                    "name": project.name,
                }

            api_key_project_id = None if org_scoped else project.id
            api_key_qs = ApiKey.objects.filter(
                org=org, name=api_key_name, project_id=api_key_project_id
            ).order_by("created_at")
            if api_key_qs.count() > 1:
                raise CommandError(
                    "ambiguous api key name match; multiple keys exist in this org with this name"
                )

            api_key = api_key_qs.first()
            if api_key is None:
                try:
                    api_key, minted_token = create_api_key(
                        org=org,
                        name=api_key_name,
                        scopes=api_scopes,
                        project_id=api_key_project_id,
                        created_by_user=pm_user,
                    )
                except ValueError as exc:
                    raise CommandError(str(exc)) from exc

                summary["api_key"] = {
                    "action": "created",
                    "id": str(api_key.id),
                    "name": api_key.name,
                    "prefix": api_key.prefix,
                    "project_id": str(api_key.project_id) if api_key.project_id else None,
                    "scopes": list(api_key.scopes or []),
                }
            else:
                summary["api_key"] = {
                    "action": "reused",
                    "id": str(api_key.id),
                    "name": api_key.name,
                    "prefix": api_key.prefix,
                    "project_id": str(api_key.project_id) if api_key.project_id else None,
                    "scopes": list(api_key.scopes or []),
                }
                if reveal or token_file_path is not None:
                    summary["warnings"].append(
                        "API key token not available for reused keys (secrets are shown only at "
                        "mint/rotate time)"
                    )

            if minted_token is not None and token_file_path is not None:
                _write_token_file(
                    path=token_file_path,
                    payload={
                        "token": minted_token.token,
                        "org_id": summary["org"]["id"],
                        "project_id": summary["api_key"]["project_id"],
                        "key_prefix": minted_token.prefix,
                    },
                )
                token_written_to = str(token_file_path.expanduser().resolve())

        if minted_token is not None and reveal:
            summary["api_key"]["token"] = minted_token.token

        summary["api_key"]["token_written_to"] = token_written_to

        self.stdout.write(json.dumps(summary))
