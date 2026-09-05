"""
Sérialiseurs KYC.

Deux familles :
- Submit (vendeur/livreur) : seuls les documents et leur type sont acceptés.
  Aucun champ d'identité (seller_id, driver_id...) n'est accepté : le
  propriétaire est toujours `request.user`, imposé par la vue. Toute tentative
  du frontend de fournir un propriétaire est donc ignorée par DRF.
- Lecture admin : expose le propriétaire et des URLs pré-signées à courte
  durée vers les pièces (aucun accès public brut).
"""
from rest_framework import serializers
from .models import DriverKYC, SellerKYC
from .storage import signed_url

KYC_DOCUMENT_TYPES = [
    ("cni", "Carte nationale d'identité"),
    ("passeport", "Passeport"),
    ("permis", "Permis de conduire"),
    ("titre_sejour", "Titre de séjour"),
    ("autre", "Autre document"),
]

# Le frontend ne choisit JAMAIS le propriétaire d'un dossier : il est
# toujours `request.user`. Ces champs sont interdits — leur présence vaut
# erreur (pas un simple silence) pour ne laisser aucun doute.
FORBIDDEN_OWNER_FIELDS = {"seller", "seller_id", "driver", "driver_id", "owner", "owner_id", "user", "user_id"}


class _KYCDocumentSubmitSerializer(serializers.Serializer):
    """Accepte uniquement les documents et leur type — jamais le propriétaire."""

    document_type = serializers.ChoiceField(choices=KYC_DOCUMENT_TYPES)
    document_front = serializers.FileField(error_messages={"required": "La pièce recto est requise."})
    document_back = serializers.FileField(error_messages={"required": "La pièce verso est requise."})

    def validate_document_front(self, value):
        return self._validate_document(value)

    def validate_document_back(self, value):
        return self._validate_document(value)

    def validate(self, attrs):
        provided = set(self.initial_data.keys()).intersection(FORBIDDEN_OWNER_FIELDS)
        if provided:
            raise serializers.ValidationError(
                f"Champs interdits : {', '.join(sorted(provided))}. Le propriétaire "
                "du dossier est déterminé par le compte connecté, jamais par le client."
            )
        return attrs

    @staticmethod
    def _validate_document(value):
        if value.size > 8 * 1024 * 1024:
            raise serializers.ValidationError("Chaque pièce doit faire moins de 8 Mo.")
        return value


class SellerKYCSubmitSerializer(_KYCDocumentSubmitSerializer):
    pass


class DriverKYCSubmitSerializer(_KYCDocumentSubmitSerializer):
    pass


class SellerKYCSerializer(serializers.ModelSerializer):
    seller_name = serializers.SerializerMethodField()
    seller_email = serializers.EmailField(source="seller.email", read_only=True)
    seller_phone = serializers.CharField(source="seller.phone", read_only=True)
    document_front_url = serializers.SerializerMethodField()
    document_back_url = serializers.SerializerMethodField()

    class Meta:
        model = SellerKYC
        fields = [
            "id", "seller", "seller_name", "seller_email", "seller_phone",
            "document_type", "document_front", "document_back",
            "document_front_url", "document_back_url",
            "status", "rejection_reason", "submitted_at", "verified_at",
            "created_at", "updated_at",
        ]
        read_only_fields = fields

    def get_seller_name(self, obj):
        return obj.seller.get_full_name() or obj.seller.email

    def get_document_front_url(self, obj):
        return signed_url(obj.document_front) if obj.document_front else ""

    def get_document_back_url(self, obj):
        return signed_url(obj.document_back) if obj.document_back else ""


class DriverKYCSerializer(serializers.ModelSerializer):
    driver_name = serializers.SerializerMethodField()
    driver_email = serializers.EmailField(source="driver.email", read_only=True)
    driver_phone = serializers.CharField(source="driver.phone", read_only=True)
    document_front_url = serializers.SerializerMethodField()
    document_back_url = serializers.SerializerMethodField()

    class Meta:
        model = DriverKYC
        fields = [
            "id", "driver", "driver_name", "driver_email", "driver_phone",
            "document_type", "document_front", "document_back",
            "document_front_url", "document_back_url",
            "status", "rejection_reason", "submitted_at", "verified_at",
            "created_at", "updated_at",
        ]
        read_only_fields = fields

    def get_driver_name(self, obj):
        return obj.driver.get_full_name() or obj.driver.email

    def get_document_front_url(self, obj):
        return signed_url(obj.document_front) if obj.document_front else ""

    def get_document_back_url(self, obj):
        return signed_url(obj.document_back) if obj.document_back else ""