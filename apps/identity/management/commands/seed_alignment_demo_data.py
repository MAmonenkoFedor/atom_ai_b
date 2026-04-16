from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.identity.models import Role, UserRole
from apps.organizations.models import Organization, OrganizationMember
from apps.orgstructure.models import OrgUnit, OrgUnitMember, UserManagerLink
from apps.projects.models import Project, ProjectMember


class Command(BaseCommand):
    help = "Seed demo data for backend-frontend alignment smoke flow."

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            default="Pass12345!",
            help="Password for all seeded users.",
        )

    def _ensure_user(self, user_model, username, email, first_name, last_name, password):
        user, _ = user_model.objects.get_or_create(
            username=username,
            defaults={
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
                "is_active": True,
            },
        )
        user.email = email
        user.first_name = first_name
        user.last_name = last_name
        user.is_active = True
        user.set_password(password)
        user.save(
            update_fields=["email", "first_name", "last_name", "is_active", "password"]
        )
        return user

    def _ensure_role(self, code, name):
        role, _ = Role.objects.get_or_create(code=code, defaults={"name": name})
        return role

    def handle(self, *args, **options):
        password = options["password"]
        user_model = get_user_model()

        organization, _ = Organization.objects.get_or_create(
            slug="atom-demo",
            defaults={"name": "ATOM Demo Company", "is_active": True},
        )
        organization.name = "ATOM Demo Company"
        organization.is_active = True
        organization.save(update_fields=["name", "is_active"])

        role_employee = self._ensure_role("employee", "Employee")
        role_manager = self._ensure_role("manager", "Manager")
        role_company_admin = self._ensure_role("company_admin", "Company Admin")
        role_super_admin = self._ensure_role("super_admin", "Super Admin")

        super_admin = self._ensure_user(
            user_model,
            username="super_admin_test",
            email="super_admin_test@atom.local",
            first_name="Super",
            last_name="Admin",
            password=password,
        )
        company_admin = self._ensure_user(
            user_model,
            username="company_admin_test",
            email="company_admin_test@atom.local",
            first_name="Company",
            last_name="Admin",
            password=password,
        )
        manager = self._ensure_user(
            user_model,
            username="manager_demo",
            email="manager_demo@atom.local",
            first_name="Mila",
            last_name="Stone",
            password=password,
        )
        employee_1 = self._ensure_user(
            user_model,
            username="employee_demo_1",
            email="employee_demo_1@atom.local",
            first_name="Alex",
            last_name="Kim",
            password=password,
        )
        employee_2 = self._ensure_user(
            user_model,
            username="employee_demo_2",
            email="employee_demo_2@atom.local",
            first_name="Chris",
            last_name="Vale",
            password=password,
        )

        UserRole.objects.get_or_create(user=super_admin, role=role_super_admin, organization=None)
        UserRole.objects.get_or_create(
            user=company_admin, role=role_company_admin, organization=organization
        )
        UserRole.objects.get_or_create(user=manager, role=role_manager, organization=organization)
        UserRole.objects.get_or_create(user=employee_1, role=role_employee, organization=organization)
        UserRole.objects.get_or_create(user=employee_2, role=role_employee, organization=organization)

        for user, title in [
            (company_admin, "Company Admin"),
            (manager, "Department Manager"),
            (employee_1, "Specialist"),
            (employee_2, "Specialist"),
        ]:
            OrganizationMember.objects.get_or_create(
                organization=organization,
                user=user,
                defaults={"job_title": title, "is_active": True},
            )

        engineering, _ = OrgUnit.objects.get_or_create(
            organization=organization,
            name="Engineering",
            defaults={"code": "ENG", "is_active": True},
        )
        marketing, _ = OrgUnit.objects.get_or_create(
            organization=organization,
            name="Marketing",
            defaults={"code": "MKT", "is_active": True},
        )

        OrgUnitMember.objects.get_or_create(
            org_unit=engineering,
            user=manager,
            defaults={"position": "Team Lead", "is_lead": True},
        )
        OrgUnitMember.objects.get_or_create(
            org_unit=engineering,
            user=employee_1,
            defaults={"position": "Engineer", "is_lead": False},
        )
        OrgUnitMember.objects.get_or_create(
            org_unit=marketing,
            user=employee_2,
            defaults={"position": "Marketer", "is_lead": False},
        )

        UserManagerLink.objects.get_or_create(
            organization=organization,
            employee=employee_1,
            defaults={"manager": manager},
        )
        UserManagerLink.objects.get_or_create(
            organization=organization,
            employee=employee_2,
            defaults={"manager": manager},
        )

        project_specs = [
            ("Customer Portal", "active", company_admin),
            ("Cost Reduction", "on_hold", manager),
            ("Growth Campaign", "completed", manager),
            ("Legacy Migration", "archived", company_admin),
        ]
        seeded_projects = []
        for name, status, owner in project_specs:
            project, _ = Project.objects.get_or_create(
                organization=organization,
                name=name,
                defaults={
                    "description": f"{name} demo project",
                    "status": status,
                    "created_by": owner,
                },
            )
            project.description = f"{name} demo project"
            project.status = status
            project.created_by = owner
            project.save(update_fields=["description", "status", "created_by", "updated_at"])
            seeded_projects.append(project)

        member_matrix = [
            (seeded_projects[0], company_admin, ProjectMember.ROLE_OWNER),
            (seeded_projects[0], manager, ProjectMember.ROLE_EDITOR),
            (seeded_projects[0], employee_1, ProjectMember.ROLE_VIEWER),
            (seeded_projects[1], manager, ProjectMember.ROLE_OWNER),
            (seeded_projects[1], employee_1, ProjectMember.ROLE_EDITOR),
            (seeded_projects[2], manager, ProjectMember.ROLE_OWNER),
            (seeded_projects[2], employee_2, ProjectMember.ROLE_EDITOR),
            (seeded_projects[3], company_admin, ProjectMember.ROLE_OWNER),
        ]
        for project, user, role in member_matrix:
            member, _ = ProjectMember.objects.get_or_create(
                project=project,
                user=user,
                defaults={"role": role, "is_active": True},
            )
            if member.role != role or not member.is_active:
                member.role = role
                member.is_active = True
                member.save(update_fields=["role", "is_active"])

        self.stdout.write(self.style.SUCCESS("Alignment demo data is ready."))
        self.stdout.write(f"Organization: {organization.name} (slug={organization.slug})")
        self.stdout.write(f"Engineering department_id: {engineering.id}")
        self.stdout.write(f"Marketing department_id: {marketing.id}")
        self.stdout.write("Users:")
        self.stdout.write(f"  super_admin_test / {password}")
        self.stdout.write(f"  company_admin_test / {password}")
        self.stdout.write(f"  manager_demo / {password}")
        self.stdout.write(f"  employee_demo_1 / {password}")
        self.stdout.write(f"  employee_demo_2 / {password}")
