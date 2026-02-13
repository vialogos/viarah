from __future__ import annotations

from django.db import migrations


def forwards(apps, schema_editor):
    del schema_editor

    OrgMembership = apps.get_model("identity", "OrgMembership")
    OrgInvite = apps.get_model("identity", "OrgInvite")
    Person = apps.get_model("identity", "Person")
    User = apps.get_model("identity", "User")

    for membership in OrgMembership.objects.all().iterator():
        user = User.objects.filter(id=membership.user_id).first()
        if user is None:
            continue

        person = Person.objects.filter(org_id=membership.org_id, user_id=membership.user_id).first()
        if person is None:
            person = Person.objects.create(
                org_id=membership.org_id,
                user_id=membership.user_id,
                email=(user.email or "").strip().lower() or None,
                preferred_name=(getattr(user, "display_name", "") or "").strip(),
                title=(membership.title or "").strip(),
                skills=list(getattr(membership, "skills", None) or []),
                bio=(membership.bio or "").strip(),
            )
            continue

        fields_to_update: set[str] = set()

        if not getattr(person, "email", None):
            cleaned_email = (user.email or "").strip().lower()
            if cleaned_email:
                person.email = cleaned_email
                fields_to_update.add("email")

        if not (getattr(person, "preferred_name", "") or "").strip():
            display_name = (getattr(user, "display_name", "") or "").strip()
            if display_name:
                person.preferred_name = display_name
                fields_to_update.add("preferred_name")

        if not (getattr(person, "title", "") or "").strip() and (membership.title or "").strip():
            person.title = (membership.title or "").strip()
            fields_to_update.add("title")

        if not (getattr(person, "skills", None) or []) and (getattr(membership, "skills", None) or []):
            person.skills = list(getattr(membership, "skills", None) or [])
            fields_to_update.add("skills")

        if not (getattr(person, "bio", "") or "").strip() and (membership.bio or "").strip():
            person.bio = (membership.bio or "").strip()
            fields_to_update.add("bio")

        if fields_to_update:
            person.save(update_fields=sorted(fields_to_update | {"updated_at"}))

    for invite in OrgInvite.objects.filter(person_id__isnull=True).iterator():
        email = (invite.email or "").strip().lower() or None
        if email is None:
            continue

        person = Person.objects.filter(org_id=invite.org_id, email=email).first()
        if person is None:
            person = Person.objects.create(org_id=invite.org_id, email=email)

        invite.person_id = person.id
        invite.save(update_fields=["person"])


def backwards(apps, schema_editor):
    del apps, schema_editor


class Migration(migrations.Migration):
    dependencies = [
        ("identity", "0003_orginvite_message_person_orginvite_person_and_more"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
