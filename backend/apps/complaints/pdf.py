"""
Génération minimale de PDF pour le dossier de réclamation (app sans dépendance).

rappel : reportlab n'est pas dans les dépendances du projet et présente un
risque de compatibilité (wheels) ; ce module écrit un PDF valide en pur Python
(Hélices de base / latin-1), suffisant pour l'export du dossier de plainte.
"""
from django.utils import timezone


def next_daily_reference(qs, prefix):
    """Référence du jour : <PREFIXE>-YYYYMMDD-NNNNNN (séquence par jour)."""
    today = timezone.now().strftime("%Y%m%d")
    count_so_far = qs.filter(reference__startswith=f"{prefix}-{today}").count()
    return f"{prefix}-{today}-{count_so_far + 1:06d}"


# --- Géométrie A4 (points) ---
PAGE_W, PAGE_H = 595, 842
MARGIN = 50
CONTENT_W = PAGE_W - 2 * MARGIN


def _encode_latin1(text):
    """Convertit un texte en latin-1 (WinAnsi) sans lever (remplace sinon)."""
    return str(text).encode("cp1252", errors="replace").decode("cp1252")


def _esc(text):
    return _encode_latin1(text).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _lines(text, max_chars=110):
    """Découpe un texte en lignes physiques (mots + sauts de ligne)."""
    text = _encode_latin1(text)
    if not text:
        yield ""
        return
    for natural in text.splitlines() or [""]:
        current = ""
        for word in natural.split(" "):
            candidate = f"{current} {word}".strip()
            if len(candidate) > max_chars and current:
                yield current
                current = word
            else:
                current = candidate
        yield current


class PDFBuilder:
    """Builder minimal de PDF : texte + lignes horizontales, pagination auto."""

    def __init__(self):
        self.pages = []
        self._current = []
        self._y = 800
        self._page_number = 1
        self._title = ""
        self._subtitle = ""
        self.footer_note = ""

    def _flush(self):
        self.pages.append("\n".join(self._current))
        self._current = []
        self._y = 800
        self._page_number += 1

    def header(self, title, subtitle=""):
        self._title = title
        self._subtitle = subtitle
        # Bandeau supérieur.
        self._current = [
            "0.14 0.2 0.33 rg",                       # bleu nuit SUNU MALL
            f"50 {PAGE_H - 60} {CONTENT_W} 40 re f",
            "1 1 1 rg",
            f"BT /F2 14 Tf 60 {PAGE_H - 47} Td (SUNU MALL) Tj ET",
        ]
        # Curseur d'écriture placé sous le bandeau.
        self._y = PAGE_H - 60 - 14

    def hline(self, thickness=1):
        """Ligne de séparation horizontale à la position courante."""
        y = self._y - 6
        self._current.append(f"0.55 0.58 0.62 RG {thickness} w {MARGIN} {y} m {MARGIN + CONTENT_W} {y} l S")
        self._y = y - 14

    def text(self, line, size=9, leading=13, bold=False):
        if self._y < 42:
            self._flush()
        self._current.append(
            f"BT /{'F2' if bold else 'F1'} {size} Tf {MARGIN} {self._y} Td "
            f"({_esc(line)}) Tj ET"
        )
        self._y -= leading

    def paragraph(self, text, size=9, leading=13, label=None):
        """Texte (éventuellement étiqueté) avec saut de ligne automatique."""
        if label is not None:
            self.text(label, size=size, leading=leading, bold=True)
        for line in _lines(text):
            self.text(line, size=size, leading=leading)

    def key_value(self, key, value, size=9):
        """Affiche `Clé : valeur` avec la clé en gras."""
        self.text(f"{key} : {value}", size=size)

    def finish(self):
        """Termine la dernière page (pied de page + pagination) et retourne les octets."""
        y = 28
        self._current.append(f"0.75 0.78 0.82 RG 0.5 w {MARGIN} {y} m {MARGIN + CONTENT_W} {y} l S")
        generated = timezone.now().strftime("%d/%m/%Y %H:%M")
        self._current.append(
            f"BT /F1 8 Tf {MARGIN} 18 Td "
            f"(Généré le {generated} — {self.footer_note} — Page {self._page_number}) Tj ET"
        )
        self.pages.append("\n".join(self._current))
        return build_pdf_bytes(self.pages)


def build_pdf_bytes(pages):
    """Assemble les pages en un PDF valide (objets, xref, trailer)."""
    font1 = "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
    font2 = "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>"
    page_objects = []
    stream_objects = []
    obj_index = 5
    for _ in pages:
        page_objects.append(obj_index)
        obj_index += 1
        stream_objects.append(obj_index)
        obj_index += 1

    kids = " ".join(f"{i} 0 R" for i in page_objects)
    catalog = "<< /Type /Catalog /Pages 2 0 R >>"
    pages_ref = (
        f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} "
        f"/MediaBox [0 0 {PAGE_W} {PAGE_H}] >>"
    )

    serialize = [
        f"{catalog}\nendobj",
        f"{pages_ref}\nendobj",
        f"<< /Type /Font {font1} >>\nendobj",
        f"<< /Type /Font {font2} >>\nendobj",
    ]

    for content, page_obj, stream_obj in zip(pages, page_objects, stream_objects):
        page = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_W} {PAGE_H}] "
            f"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents {stream_obj} 0 R >>\nendobj"
        )
        serialize.append(page)
        encoded = content.encode("cp1252", errors="replace")
        serialize.append(
            f"<< /Length {len(encoded)} >>\nstream\n".encode("latin1")
            + encoded
            + b"\nendstream\nendobj"
        )

    body = b""
    offsets = []
    for obj in serialize:
        offsets.append(len(body))
        if isinstance(obj, bytes):
            body += obj
        else:
            body += obj.encode("latin1")
        body += b"\n"

    xref_pos = len(body)
    xref = (
        f"xref\n0 {len(offsets) + 1}\n"
        "0000000000 65535 f \n"
        + "".join(f"{off:010d} 00000 n \n" for off in offsets)
    )
    trailer = (
        f"trailer\n<< /Size {len(offsets) + 1} /Root 1 0 R >>\n"
        "startxref\n"
        f"{xref_pos}\n"
        "%%EOF\n"
    )
    return b"%PDF-1.4\n" + body + xref.encode("latin1") + trailer.encode("latin1")


def complaint_dossier_pdf(complaint, timeline, attachments):
    """Dossier PDF lisible d'une plainte : en-tête, fiche, description +
    historique de traitement complet."""
    b = PDFBuilder()
    b.header("SUNU MALL — Dossier de réclamation", complaint.reference)
    b.footer_note = complaint.reference
    b.hline()
    b.text(complaint.reference, size=13, bold=True, leading=20)
    b.key_value("Déposée le", complaint.created_at.strftime("%d/%m/%Y à %H:%M"))
    b.key_value("Par", complaint.complainant.get_full_name() or complaint.complainant.email)
    b.key_value("Catégorie", complaint.get_category_display())
    b.key_value("Priorité", complaint.get_priority_display())
    b.key_value("Statut", complaint.get_status_display())
    if complaint.order:
        b.key_value("Commande", str(complaint.order.id))
    if complaint.store:
        b.key_value("Boutique", complaint.store.name)
    if complaint.priority == complaint.Priority.CRITICAL:
        b.paragraph("Plainte marquée CRITIQUE — traitement prioritaire demandé.", label="ALERTE")
    b.hline()
    b.paragraph(complaint.subject, label="Objet")
    b.paragraph(complaint.description or "", label="Description")
    if complaint.resolution_decision:
        b.key_value("Décision", complaint.get_resolution_decision_display())
    if complaint.resolution_note:
        b.paragraph(complaint.resolution_note, label="Note de résolution")
    b.hline()
    b.paragraph("Suivi chronologique du traitement :", label="Historique")
    for entry in timeline:
        actor = entry.actor.get_full_name() or entry.actor.email if entry.actor else "Système"
        line = f"[{entry.created_at:%d/%m/%Y %H:%M}] {actor} — {entry.get_action_display()}"
        b.text(line, size=9)
        if entry.note:
            b.paragraph(entry.note or "", size=8, leading=11, label="    ")
    if attachments:
        b.hline()
        b.paragraph("Pièces jointes :", label="Pièces jointes")
        for a in attachments:
            b.text(f"- {a.filename} ({a.size_bytes} octets)")
    return b.finish()