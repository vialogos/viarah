from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("identity", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
            DO $$
            BEGIN
              IF to_regclass('public.identity_orgmembership') IS NULL THEN
                RETURN;
              END IF;

              -- Legacy columns that may exist in some environments due to historic
              -- migration drift. If present and NOT NULL, they can break inserts
              -- because the current Django model does not include them.
              IF EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'identity_orgmembership'
                  AND column_name = 'availability_notes'
              ) THEN
                EXECUTE 'ALTER TABLE public.identity_orgmembership ALTER COLUMN availability_notes DROP NOT NULL';
              END IF;

              IF EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'identity_orgmembership'
                  AND column_name = 'availability_status'
              ) THEN
                EXECUTE 'ALTER TABLE public.identity_orgmembership ALTER COLUMN availability_status DROP NOT NULL';
              END IF;

              IF EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'identity_orgmembership'
                  AND column_name = 'bio'
              ) THEN
                EXECUTE 'ALTER TABLE public.identity_orgmembership ALTER COLUMN bio DROP NOT NULL';
              END IF;

              IF EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'identity_orgmembership'
                  AND column_name = 'skills'
              ) THEN
                EXECUTE 'ALTER TABLE public.identity_orgmembership ALTER COLUMN skills DROP NOT NULL';
              END IF;

              IF EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'identity_orgmembership'
                  AND column_name = 'title'
              ) THEN
                EXECUTE 'ALTER TABLE public.identity_orgmembership ALTER COLUMN title DROP NOT NULL';
              END IF;
            END $$;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]

