from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.identity.models import Role, UserRole


class Command(BaseCommand):
    help = "Create/update test credentials for frontend alignment sprint."

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            default="Pass12345!",
            help="Password for both test users.",
        )

    def handle(self, *args, **options):
        password = options["password"]
        user_model = get_user_model()

        role_company_admin, _ = Role.objects.get_or_create(
            code="company_admin",
            defaults={"name": "Company Admin"},
        )
        role_super_admin, _ = Role.objects.get_or_create(
            code="super_admin",
            defaults={"name": "Super Admin"},
        )
        role_employee, _ = Role.objects.get_or_create(
            code="employee",
            defaults={"name": "Employee"},
        )
        role_manager, _ = Role.objects.get_or_create(
            code="manager",
            defaults={"name": "Manager"},
        )

        employee_user, _ = user_model.objects.get_or_create(
            username="employee_test",
            defaults={
                "email": "employee_test@atom.local",
                "first_name": "Alex",
                "last_name": "Kim",
                "is_active": True,
            },
        )
        employee_user.email = "employee_test@atom.local"
        employee_user.is_active = True
        employee_user.set_password(password)
        employee_user.save(
            update_fields=["email", "is_active", "password", "first_name", "last_name"]
        )

        manager_user, _ = user_model.objects.get_or_create(
            username="manager_test",
            defaults={
                "email": "manager_test@atom.local",
                "first_name": "Maria",
                "last_name": "Smirnova",
                "is_active": True,
            },
        )
        manager_user.email = "manager_test@atom.local"
        manager_user.is_active = True
        manager_user.set_password(password)
        manager_user.save(
            update_fields=["email", "is_active", "password", "first_name", "last_name"]
        )

        company_admin, _ = user_model.objects.get_or_create(
            username="company_admin_test",
            defaults={
                "email": "company_admin_test@atom.local",
                "first_name": "Company",
                "last_name": "Admin",
                "is_active": True,
            },
        )
        company_admin.email = "company_admin_test@atom.local"
        company_admin.is_active = True
        company_admin.set_password(password)
        company_admin.save(
            update_fields=["email", "is_active", "password", "first_name", "last_name"]
        )

        super_admin, _ = user_model.objects.get_or_create(
            username="super_admin_test",
            defaults={
                "email": "super_admin_test@atom.local",
                "first_name": "Super",
                "last_name": "Admin",
                "is_active": True,
            },
        )
        super_admin.email = "super_admin_test@atom.local"
        super_admin.is_active = True
        super_admin.set_password(password)
        super_admin.save(
            update_fields=["email", "is_active", "password", "first_name", "last_name"]
        )

        UserRole.objects.get_or_create(user=company_admin, role=role_company_admin, organization=None)
        UserRole.objects.get_or_create(user=super_admin, role=role_super_admin, organization=None)
        UserRole.objects.get_or_create(user=employee_user, role=role_employee, organization=None)
        UserRole.objects.get_or_create(user=manager_user, role=role_manager, organization=None)

        self.stdout.write(self.style.SUCCESS("Test credentials are ready:"))
        self.stdout.write(f"  employee      -> username: {employee_user.username}")
        self.stdout.write(f"  manager       -> username: {manager_user.username}")
        self.stdout.write(f"  company_admin -> username: {company_admin.username}")
        self.stdout.write(f"  super_admin   -> username: {super_admin.username}")
        self.stdout.write(f"  password      -> {password}")
