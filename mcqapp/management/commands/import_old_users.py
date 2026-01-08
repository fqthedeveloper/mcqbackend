import sqlite3
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.conf import settings
from django.utils.crypto import get_random_string

User = get_user_model()


class Command(BaseCommand):
    help = "Import users from old Django SQLite database"

    def handle(self, *args, **kwargs):
        old_db_path = "old_db.sqlite3"  # 🔴 CHANGE IF NEEDED

        self.stdout.write("Connecting to old database...")

        conn = sqlite3.connect(old_db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT email, username, first_name, last_name, password, is_active, is_staff, is_superuser
            FROM auth_user
        """)

        rows = cursor.fetchall()
        created = 0
        skipped = 0

        for row in rows:
            email, username, first_name, last_name, password, is_active, is_staff, is_superuser = row

            if not email:
                skipped += 1
                continue

            if User.objects.filter(email=email).exists():
                skipped += 1
                continue

            user = User(
                email=email,
                username=username or email,
                first_name=first_name or "",
                last_name=last_name or "",
                is_active=is_active,
                is_staff=is_staff,
                is_superuser=is_superuser,
                user_type='student',  # 👈 default
                force_password_change=True
            )

            # ⚠️ IMPORTANT
            user.password = password  # hashed already
            user.save()

            created += 1

        conn.close()

        self.stdout.write(self.style.SUCCESS(
            f"Import completed: {created} users created, {skipped} skipped"
        ))
