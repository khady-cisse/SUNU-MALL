"""
Provisionne (ou met à jour) un compte administrateur de la plateforme.

Usage :
    python manage.py create_admin
    python manage.py create_admin --email boss@sunumall.com --password "MdpFort@2026"
    python manage.py create_admin --super-admin
    python manage.py create_admin --email admin.kyc@sunumall.com --role admin_kyc
    python manage.py create_admin --role admin_finance --role admin_support
    python manage.py create_admin --role all

Idempotent : si l'email existe déjà, le compte est réactivé, marqué vérifié
et recevra les rôles d'administration demandés (les autres rôles sont
conservés).

Rôles acceptés (--role, répétable) : super_admin, admin_kyc, admin_support,
admin_finance, admin_marketplace, admin_delivery ou "all" (tous les rôles
d'administration). Sans --role, le rôle maître "admin" est accordé par défaut
(rétrocompatible).

Par défaut :
    email    admin@sunumall.com
    username admin@sunumall.com
    password Admin@12345   (à changer après la première connexion)
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.users.models import Role, UserRole

DEFAULT_EMAIL = "admin@sunumall.com"
DEFAULT_PASSWORD = "Admin@12345"


class Command(BaseCommand):
    help = "Crée ou met à jour un compte administrateur de Sunu Mall."

    def add_arguments(self, parser):
        parser.add_argument("--email", default=DEFAULT_EMAIL, help="Adresse email du compte admin.")
        parser.add_argument("--username", default=None, help="Nom d'utilisateur (défaut : l'email).")
        parser.add_argument("--password", default=DEFAULT_PASSWORD, help="Mot de passe (défaut documenté).")
        parser.add_argument(
            "--first-name", default="Sunu Mall", help="Prénom du compte (défaut : « Sunu Mall »)."
        )
        parser.add_argument(
            "--last-name", default="Administration", help="Nom du compte (défaut : « Administration »)."
        )
        parser.add_argument(
            "--role",
            action="append",
            dest="roles",
            default=None,
            help=(
                "Rôle d'administration à accorder (répétable). Options : "
                + ", ".join(Role.ADMIN_ROLES)
                + " ou 'all'. Défaut si absent : 'admin'."
            ),
        )
        parser.add_argument(
            "--super-admin",
            action="store_true",
            help="Accorde aussi le rôle super_admin (accès complet au centre de contrôle).",
        )

    def handle(self, *args, **options):
        User = get_user_model()
        email = options["email"].lower().strip()
        username = options["username"] or email

        # Collection des rôles d'administration à garantir (validés).
        if options["roles"]:
            role_names = []
            for value in options["roles"]:
                value = value.strip().lower()
                if value == "all":
                    role_names.extend(Role.ADMIN_ROLES)
                elif value in Role.ADMIN_ROLES:
                    role_names.append(value)
                else:
                    raise CommandError(
                        f"Rôle inconnu : {value}. Attendu parmi {', '.join(Role.ADMIN_ROLES)} ou 'all'."
                    )
            # Préserver l'ordre canonique et évincer les doublons.
            role_names = list(dict.fromkeys(role_names))
        else:
            role_names = [Role.RoleName.ADMIN]

        if options["super_admin"] and Role.RoleName.SUPER_ADMIN not in role_names:
            role_names.append(Role.RoleName.SUPER_ADMIN)

        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                "username": username,
                "email": email,
                "first_name": options["first_name"],
                "last_name": options["last_name"],
                "is_active": True,
                "is_verified": True,
            },
        )
        if created:
            user.set_password(options["password"])
        else:
            # Un compte existant : on le réactive et on le passe vérifié, sans
            # écraser son mot de passe (sauf si fourni explicitement, voir ci-dessous).
            changed = []
            if not user.is_active:
                user.is_active = True
                changed.append("réactivé")
            if not user.is_verified:
                user.is_verified = True
                changed.append("marqué vérifié")
            if options["password"] != DEFAULT_PASSWORD:
                user.set_password(options["password"])
                changed.append("mot de passe mis à jour")
            if not user.has_usable_password():
                user.set_password(options["password"])

        user.save()

        granted = []
        for role_name in role_names:
            role, _ = Role.objects.get_or_create(name=role_name)
            _, was_granted = UserRole.objects.get_or_create(user=user, role=role)
            if was_granted:
                granted.append(str(role))

        message = "créé" if created else "mis à jour"
        self.stdout.write(self.style.SUCCESS(
            f"Compte admin {message} : {email}"
        ))
        if granted:
            self.stdout.write(self.style.WARNING(f"Rôle(s) ajouté(s) : {', '.join(granted)}"))
        self.stdout.write(
            f"Rôles : {', '.join(role_names)}"
        )
        self.stdout.write(
            f"Connexion : {email} / {options['password'] if options['password'] != DEFAULT_PASSWORD else DEFAULT_PASSWORD}"
        )