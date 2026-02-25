import hashlib
import secrets
import uuid
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone

from work_items.models import ProgressPolicy


def person_avatar_upload_to(instance: "Person", filename: str) -> str:
    cleaned = (filename or "avatar").strip().replace("/", "_").replace("\\", "_")
    token = secrets.token_hex(8)
    return f"avatars/{instance.org_id}/people/{instance.id}/{token}-{cleaned}"


def org_logo_upload_to(instance: "Org", filename: str) -> str:
    cleaned = (filename or "logo").strip().replace("/", "_").replace("\\", "_")
    token = secrets.token_hex(8)
    return f"logos/orgs/{instance.id}/{token}-{cleaned}"


class UserManager(BaseUserManager):
    def create_user(self, email: str, password: str | None = None, **extra_fields):
        if not email:
            raise ValueError("email is required")

        normalized_email = self.normalize_email(email).strip().lower()
        user = self.model(email=normalized_email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email: str, password: str, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(email=email, password=password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    display_name = models.CharField(max_length=200, blank=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    def __str__(self) -> str:
        return self.email


class Org(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    logo_file = models.FileField(upload_to=org_logo_upload_to, max_length=500, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.name


def default_workflow_stage_template() -> list[dict]:
    return [
        {
            "name": "Backlog",
            "category": "backlog",
            "progress_percent": 0,
            "is_qa": False,
            "counts_as_wip": False,
        },
        {
            "name": "In Progress",
            "category": "in_progress",
            "progress_percent": 33,
            "is_qa": False,
            "counts_as_wip": True,
        },
        {
            "name": "QA",
            "category": "qa",
            "progress_percent": 67,
            "is_qa": True,
            "counts_as_wip": True,
        },
        {
            "name": "Done",
            "category": "done",
            "progress_percent": 100,
            "is_qa": False,
            "counts_as_wip": False,
        },
    ]


class GlobalDefaults(models.Model):
    """Instance-wide defaults used as fallbacks when org overrides are unset."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    key = models.CharField(max_length=50, unique=True, default="default")

    project_progress_policy = models.CharField(
        max_length=30,
        choices=ProgressPolicy.choices,
        default=ProgressPolicy.SUBTASKS_ROLLUP,
    )
    workflow_stage_template = models.JSONField(default=default_workflow_stage_template, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["key", "updated_at"]),
        ]


class OrgDefaults(models.Model):
    """Org-level overrides for instance defaults (nullable fields inherit from global defaults)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    org = models.OneToOneField(Org, on_delete=models.CASCADE, related_name="defaults")

    project_progress_policy = models.CharField(
        max_length=30, choices=ProgressPolicy.choices, null=True, blank=True
    )
    default_project_workflow = models.ForeignKey(
        "workflows.Workflow",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    workflow_stage_template = models.JSONField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["org", "updated_at"]),
        ]


class Client(models.Model):
    """A client account record (org-scoped)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    org = models.ForeignKey(Org, on_delete=models.CASCADE, related_name="clients")
    name = models.CharField(max_length=200)
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["org", "name"], name="unique_client_name_per_org"),
        ]
        indexes = [
            models.Index(fields=["org", "name"], name="id_client_org_name_idx"),
            models.Index(fields=["org", "created_at"], name="id_client_org_created_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.org_id})"


class Person(models.Model):
    """A profile record for a person in an org.

    A Person exists before an invite is sent and may not have a linked `User` yet. Invites link to a
    Person, and invite acceptance links/creates a `User` + `OrgMembership` and associates it back to
    this Person.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    org = models.ForeignKey(Org, on_delete=models.CASCADE, related_name="people")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="people",
    )

    full_name = models.CharField(max_length=200, blank=True, default="")
    preferred_name = models.CharField(max_length=200, blank=True, default="")
    email = models.EmailField(null=True, blank=True)

    title = models.CharField(max_length=200, blank=True, default="")
    skills = models.JSONField(default=list, blank=True)
    bio = models.TextField(blank=True, default="")
    notes = models.TextField(blank=True, default="")

    timezone = models.CharField(max_length=64, blank=True, default="UTC")
    location = models.CharField(max_length=200, blank=True, default="")

    phone = models.CharField(max_length=50, blank=True, default="")
    slack_handle = models.CharField(max_length=100, blank=True, default="")
    linkedin_url = models.URLField(max_length=500, blank=True, default="")
    gitlab_username = models.CharField(max_length=200, null=True, blank=True)

    avatar_file = models.FileField(
        upload_to=person_avatar_upload_to, max_length=500, null=True, blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["org", "email"],
                condition=models.Q(email__isnull=False),
                name="unique_person_email_per_org_when_present",
            ),
            models.UniqueConstraint(
                fields=["org", "user"],
                condition=models.Q(user__isnull=False),
                name="unique_person_user_per_org_when_present",
            ),
            models.UniqueConstraint(
                fields=["org", "gitlab_username"],
                condition=models.Q(gitlab_username__isnull=False),
                name="unique_person_gitlab_username_per_org_when_present",
            ),
        ]
        indexes = [
            models.Index(fields=["org", "created_at"]),
            models.Index(fields=["org", "updated_at"]),
            models.Index(fields=["org", "full_name"]),
            models.Index(fields=["org", "email"]),
            models.Index(fields=["org", "gitlab_username"]),
            models.Index(fields=["org", "user"]),
        ]

    def __str__(self) -> str:
        base = (self.preferred_name or "").strip() or (self.full_name or "").strip()
        if base:
            return f"{base} ({self.org_id})"
        if self.email:
            return f"{self.email} ({self.org_id})"
        return f"Person {self.id} ({self.org_id})"

    def clean(self):
        self.full_name = (self.full_name or "").strip()
        self.preferred_name = (self.preferred_name or "").strip()

        if self.email is not None:
            cleaned = self.email.strip().lower()
            self.email = cleaned or None

        self.title = (self.title or "").strip()
        self.bio = (self.bio or "").strip()
        self.notes = (self.notes or "").strip()
        self.timezone = (self.timezone or "").strip() or "UTC"
        self.location = (self.location or "").strip()
        self.phone = (self.phone or "").strip()
        self.slack_handle = (self.slack_handle or "").strip()
        self.linkedin_url = (self.linkedin_url or "").strip()
        if self.gitlab_username is not None:
            cleaned = self.gitlab_username.strip().lower()
            self.gitlab_username = cleaned or None


class PersonAvailabilityWeeklyWindow(models.Model):
    """A recurring weekly availability window for a `Person`.

    Times are interpreted in the Person's `timezone` (IANA tz name, e.g. `America/New_York`).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    person = models.ForeignKey(
        Person,
        on_delete=models.CASCADE,
        related_name="availability_weekly_windows",
    )
    # 0=Monday ... 6=Sunday (Python's `date.weekday()` convention).
    weekday = models.PositiveSmallIntegerField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=models.Q(weekday__gte=0) & models.Q(weekday__lte=6),
                name="person_weekly_window_weekday_range_0_6",
            ),
            models.CheckConstraint(
                check=models.Q(start_time__lt=models.F("end_time")),
                name="person_weekly_window_start_time_lt_end_time",
            ),
            models.UniqueConstraint(
                fields=["person", "weekday", "start_time", "end_time"],
                name="person_weekly_window_unique_person_day_times",
            ),
        ]
        indexes = [
            models.Index(fields=["person", "weekday", "start_time"]),
            models.Index(fields=["person", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"WeeklyWindow {self.person_id} {self.weekday} {self.start_time}-{self.end_time}"


class PersonAvailabilityException(models.Model):
    """An exception to a Person's weekly schedule (time off or extra availability)."""

    class Kind(models.TextChoices):
        TIME_OFF = "time_off", "Time off"
        AVAILABLE = "available", "Available"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    person = models.ForeignKey(
        Person,
        on_delete=models.CASCADE,
        related_name="availability_exceptions",
    )
    kind = models.CharField(max_length=20, choices=Kind.choices)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    title = models.CharField(max_length=200, blank=True, default="")
    notes = models.TextField(blank=True, default="")
    created_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_person_availability_exceptions",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=models.Q(starts_at__lt=models.F("ends_at")),
                name="person_availability_exception_starts_at_lt_ends_at",
            ),
        ]
        indexes = [
            models.Index(fields=["person", "starts_at"]),
            models.Index(fields=["person", "created_at"]),
        ]

    def __str__(self) -> str:
        return (
            f"AvailabilityException {self.person_id} {self.kind} {self.starts_at}..{self.ends_at}"
        )


class PersonContactEntry(models.Model):
    """A dated internal contact log entry for a `Person`."""

    class Kind(models.TextChoices):
        NOTE = "note", "Note"
        CALL = "call", "Call"
        EMAIL = "email", "Email"
        MEETING = "meeting", "Meeting"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    person = models.ForeignKey(
        Person,
        on_delete=models.CASCADE,
        related_name="contact_entries",
    )
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.NOTE)
    occurred_at = models.DateTimeField()
    summary = models.CharField(max_length=200, blank=True, default="")
    notes = models.TextField(blank=True, default="")
    created_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_person_contact_entries",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["person", "occurred_at"]),
            models.Index(fields=["person", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"ContactEntry {self.person_id} {self.kind} {self.occurred_at}"


class PersonMessageThread(models.Model):
    """An internal message thread associated with a `Person`."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    person = models.ForeignKey(
        Person,
        on_delete=models.CASCADE,
        related_name="message_threads",
    )
    title = models.CharField(max_length=200)
    created_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_person_message_threads",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["person", "updated_at"]),
            models.Index(fields=["person", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"PersonMessageThread {self.person_id} {self.title}"


class PersonMessage(models.Model):
    """A message posted in a `PersonMessageThread`."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    thread = models.ForeignKey(
        PersonMessageThread,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    author_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="authored_person_messages",
    )
    body_markdown = models.TextField()
    body_html = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["thread", "created_at"]),
            models.Index(fields=["author_user", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"PersonMessage {self.thread_id} {self.author_user_id}"


class PersonRate(models.Model):
    """A rate record for a `Person` (supports history over time)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    person = models.ForeignKey(
        Person,
        on_delete=models.CASCADE,
        related_name="rates",
    )
    currency = models.CharField(max_length=3, default="USD")
    amount_cents = models.PositiveIntegerField()
    effective_date = models.DateField()
    notes = models.TextField(blank=True, default="")
    created_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_person_rates",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["person", "effective_date"]),
            models.Index(fields=["person", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"PersonRate {self.person_id} {self.amount_cents} {self.currency}"


class PersonPayment(models.Model):
    """A payment ledger entry for a `Person`."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    person = models.ForeignKey(
        Person,
        on_delete=models.CASCADE,
        related_name="payments",
    )
    currency = models.CharField(max_length=3, default="USD")
    amount_cents = models.PositiveIntegerField()
    paid_date = models.DateField()
    notes = models.TextField(blank=True, default="")
    created_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_person_payments",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["person", "paid_date"]),
            models.Index(fields=["person", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"PersonPayment {self.person_id} {self.amount_cents} {self.currency}"


class OrgMembership(models.Model):
    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        PM = "pm", "PM"
        MEMBER = "member", "Member"
        CLIENT = "client", "Client"

    class AvailabilityStatus(models.TextChoices):
        UNKNOWN = "unknown", "Unknown"
        AVAILABLE = "available", "Available"
        LIMITED = "limited", "Limited"
        UNAVAILABLE = "unavailable", "Unavailable"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    org = models.ForeignKey(Org, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="org_memberships"
    )
    role = models.CharField(max_length=20, choices=Role.choices)

    title = models.CharField(max_length=200, blank=True)
    skills = models.JSONField(default=list, blank=True)
    bio = models.TextField(blank=True)

    availability_status = models.CharField(
        max_length=20,
        choices=AvailabilityStatus.choices,
        default=AvailabilityStatus.UNKNOWN,
    )
    availability_hours_per_week = models.PositiveSmallIntegerField(null=True, blank=True)
    availability_next_available_at = models.DateField(null=True, blank=True)
    availability_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["org", "user"], name="unique_org_membership_user"),
        ]

    def __str__(self) -> str:
        return f"{self.user_id} @ {self.org_id} ({self.role})"


class OrgInvite(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    org = models.ForeignKey(Org, on_delete=models.CASCADE, related_name="invites")
    person = models.ForeignKey(
        Person,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="invites",
    )
    email = models.EmailField()
    role = models.CharField(max_length=20, choices=OrgMembership.Role.choices)
    message = models.TextField(blank=True, default="")

    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()

    created_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_org_invites",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["org", "email"]),
            models.Index(fields=["token_hash"]),
        ]

    def __str__(self) -> str:
        return f"Invite {self.email} to {self.org_id} as {self.role}"

    @classmethod
    def new_token(cls) -> str:
        return secrets.token_urlsafe(32)

    @classmethod
    def hash_token(cls, token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @classmethod
    def default_expires_at(cls):
        return timezone.now() + timedelta(days=7)

    def is_active(self) -> bool:
        if self.accepted_at is not None:
            return False
        if self.revoked_at is not None:
            return False
        return self.expires_at > timezone.now()

    def clean(self):
        self.email = self.email.strip().lower()
        self.message = (self.message or "").strip()
