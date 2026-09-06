"""
Tâches Celery de la commission : libération périodique des fonds en attente.

Les fonds des ventes livrées sont libérés (pending → available) après la
période configurée COMMISSION_RELEASE_DAYS (spec §9 : conditions de libération
remplies). Idempotente via le flag is_released de chaque vente.
"""
from celery import shared_task

from apps.commissions.services import release_pending_funds


@shared_task
def release_pending_funds_task():
    return release_pending_funds()