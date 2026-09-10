"""
Endpoints de génération de rapports administrateur (PDF/CSV).
Le fichier généré est stocké puis son URL (publique, non signée — le bucket
MinIO par défaut est en lecture publique) est renvoyée au client.

Note : le paramètre du format est volontairement nommé `fmt` (et non `format`)
car DRF réserve `?format=` à la négociation du rendu de la réponse (json/html)
— `?format=csv` déclencherait un Http404 avant même d'appeler la vue.
"""
from io import BytesIO

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.users.permissions import IsAdmin

from .generators import GENERATORS, render_csv, render_pdf


class ReportView(APIView):
    """GET /api/reports/<type>/?fmt=csv|pdf → {"url": "...", "filename": "..."}."""
    permission_classes = [IsAuthenticated, IsAdmin]
    throttle_classes = []

    def get(self, request, report_type):
        generator = GENERATORS.get(report_type)
        if generator is None:
            return Response({"detail": "Type de rapport inconnu."}, status=404)

        report_format = request.query_params.get("fmt", "csv").lower()
        if report_format not in ("csv", "pdf"):
            return Response({"detail": "Format non supporté (csv ou pdf)."}, status=400)

        report = generator()
        stamp = timezone.now().strftime("%Y%m%d-%H%M%S")
        filename = f"rapport-{report_type}-{stamp}.{report_format}"
        content = render_csv(report) if report_format == "csv" else render_pdf(report)

        stored = default_storage.save(f"reports/{filename}", ContentFile(content))
        url = default_storage.url(stored)
        return Response({"url": url, "filename": filename, "size": len(content)})