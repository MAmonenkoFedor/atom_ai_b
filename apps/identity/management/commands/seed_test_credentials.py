from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.identity.models import Role, UserRole
from apps.organizations.models import Organization, OrganizationMember
from apps.orgstructure.models import OrgUnit, OrgUnitMember
from apps.projects.models import Project, ProjectMember


class Command(BaseCommand):
    help = "Create/update test credentials for frontend alignment sprint."

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            default="AtomTest123!",
            help="Password for all seeded test users (override for your env).",
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
        role_executive, _ = Role.objects.get_or_create(
            code="executive",
            defaults={"name": "CEO / Executive"},
        )
        role_ceo, _ = Role.objects.get_or_create(
            code="ceo",
            defaults={"name": "CEO"},
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

        executive_user, _ = user_model.objects.get_or_create(
            username="executive_test",
            defaults={
                "email": "executive_test@atom.local",
                "first_name": "CEO",
                "last_name": "Test",
                "is_active": True,
            },
        )
        executive_user.email = "executive_test@atom.local"
        executive_user.is_active = True
        executive_user.set_password(password)
        executive_user.save(
            update_fields=["email", "is_active", "password", "first_name", "last_name"]
        )

        ceo_user, _ = user_model.objects.get_or_create(
            username="ceo_test",
            defaults={
                "email": "ceo_test@atom.local",
                "first_name": "CEO",
                "last_name": "Alias",
                "is_active": True,
            },
        )
        ceo_user.email = "ceo_test@atom.local"
        ceo_user.is_active = True
        ceo_user.set_password(password)
        ceo_user.save(
            update_fields=["email", "is_active", "password", "first_name", "last_name"]
        )

        UserRole.objects.get_or_create(user=company_admin, role=role_company_admin, organization=None)
        UserRole.objects.get_or_create(user=super_admin, role=role_super_admin, organization=None)
        UserRole.objects.get_or_create(user=employee_user, role=role_employee, organization=None)
        UserRole.objects.get_or_create(user=manager_user, role=role_manager, organization=None)
        UserRole.objects.get_or_create(user=executive_user, role=role_executive, organization=None)
        UserRole.objects.get_or_create(user=ceo_user, role=role_ceo, organization=None)

        # ProjectCreateSerializer defaults `organization` from OrganizationMember. Without this,
        # POST /api/projects returns 400 for users that only have UserRole rows.
        organization, _ = Organization.objects.get_or_create(
            slug="atom-demo",
            defaults={"name": "ATOM Demo Company", "is_active": True},
        )
        organization.name = "ATOM Demo Company"
        organization.is_active = True
        organization.save(update_fields=["name", "is_active"])

        for user, title in (
            (employee_user, "Test Employee"),
            (manager_user, "Test Manager"),
            (company_admin, "Company Admin"),
            (super_admin, "Super Admin"),
            (executive_user, "Executive"),
            (ceo_user, "CEO"),
        ):
            OrganizationMember.objects.get_or_create(
                organization=organization,
                user=user,
                defaults={"job_title": title, "is_active": True},
            )

        marketing_unit, _ = OrgUnit.objects.get_or_create(
            organization=organization,
            name="Marketing",
            defaults={"code": "MKT", "is_active": True},
        )
        OrgUnit.objects.get_or_create(
            organization=organization,
            name="Engineering",
            defaults={"code": "ENG", "is_active": True},
        )
        OrgUnitMember.objects.get_or_create(
            org_unit=marketing_unit,
            user=manager_user,
            defaults={"position": "Lead", "is_lead": True},
        )

        demo_project, _ = Project.objects.get_or_create(
            organization=organization,
            name="Демо: команда маркетинга",
            defaults={
                "code": "MKT-DEMO",
                "description": "Демо-проект для проверки ролей, участников и документов.",
                "status": Project.STATUS_ACTIVE,
                "created_by": manager_user,
                "primary_org_unit": marketing_unit,
            },
        )
        ProjectMember.objects.get_or_create(
            project=demo_project,
            user=manager_user,
            defaults={"role": ProjectMember.ROLE_OWNER, "is_active": True},
        )
        ProjectMember.objects.get_or_create(
            project=demo_project,
            user=employee_user,
            defaults={"role": ProjectMember.ROLE_VIEWER, "is_active": True},
        )

        self.stdout.write(self.style.SUCCESS("Test credentials are ready:"))
        self.stdout.write(f"  employee      -> username: {employee_user.username}")
        self.stdout.write(f"  manager       -> username: {manager_user.username}")
        self.stdout.write(f"  company_admin -> username: {company_admin.username}")
        self.stdout.write(f"  super_admin   -> username: {super_admin.username}")
        self.stdout.write(f"  executive     -> username: {executive_user.username}")
        self.stdout.write(f"  ceo (alias)   -> username: {ceo_user.username}")
        self.stdout.write(f"  password      -> {password}")
