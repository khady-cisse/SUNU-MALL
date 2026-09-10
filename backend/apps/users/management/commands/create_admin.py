"""
Provisionne (ou met à jour) un compte administrateur de la plateforme.

Usage :
    python manage.py create_admin
    python manage.py create_admin --email boss@sunumall.com --password "MdpFort@2026"
    python manage.py create_admin --super-admin

Idempotent : si l'email existe déjà, le compte est réactivé, marqué vérifié
et recevra le rôle d'administration demandé (les autres rôles sont conservés).

Par défaut :
    email    admin@sunumall.com
    username admin@sunumall.com
    password Admin@12345   (à changer après la première connexion)
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.users.models import Role, UserRole

DEFAULT_EMAIL = "admin@sunumall.com"
DEFAULT_PASSWORD = "Admin@12345"


class Command(BaseCommand):
    help = "Crée ou met à jour le compte administrateur principal de Sunu Mall."

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
            "--super-admin",
            action="store_true",
            help="Accorde aussi le rôle super_admin (accès complet au centre de contrôle).",
        )

    def handle(self, *args, **options):
        User = get_user_model()
        email = options["email"].lower().strip()
        username = options["username"] or email

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

        role_names = [Role.RoleName.ADMIN]
        if options["super_admin"]:
            role_names.append(Role.RoleName.SUPER_ADMIN)
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
            f"Connexion : {email} / {options['password'] if options['password'] != DEFAULT_PASSWORD else DEFAULT_PASSWORD}"
        )