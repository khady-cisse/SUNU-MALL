import { LegalLayout, LegalList } from "./LegalLayout";

export default function ConditionsUtilisationPage() {
  return (
    <LegalLayout
      badge="Conditions d'utilisation"
      title="Conditions d'utilisation"
      intro="Les règles qui s'appliquent à tous les utilisateurs de la plateforme Sunu Mall : clients, vendeurs et livreurs. En utilisant la plateforme, vous acceptez ces conditions."
      updatedAt="6 septembre 2026"
      sections={[
        {
          title: "Champ d'application",
          body: (
            <p>
              Ces conditions régissent l'accès et l'utilisation de la plateforme <strong>Sunu Mall</strong>, ses sites web et
              applications, par toute personne (le « client »), toute boutique (le « vendeur ») et tout livreur (« le livreur »).
              Elles complètent la{" "}
              <a href="/politique-de-confidentialite" className="font-medium text-orange hover:underline">
                politique de confidentialité
              </a>{" "}
              et les{" "}
              <a href="/mentions-legales" className="font-medium text-orange hover:underline">
                mentions légales
              </a>
              .
            </p>
          ),
        },
        {
          title: "Compte utilisateur",
          body: (
            <LegalList
              items={[
                <>Vous devez fournir des informations exactes et les maintenir à jour.</>,
                <>Vous êtes responsable de la confidentialité de votre mot de passe et de toute activité réalisée depuis votre compte.</>,
                <>Toute usurpation d'identité ou création de compte frauduleuse entraine la fermeture du compte.</>,
                <>Vous pouvez fermer votre compte à tout moment en contactant le service client.</>,
              ]}
            />
          ),
        },
        {
          title: "Commandes et livraison",
          body: (
            <LegalList
              items={[
                <>Une commande est validée après confirmation du paiement ou accord de paiement à la livraison.</>,
                <>Le client peut suivre sa course en temps réel et confirmer la réception avec le code remis par le livreur.</>,
                <>Le vendeur s'engage à préparer et expédier les produits dans les délais annoncés.</>,
                <>En cas de colis non livré ou de produit non conforme, le client dispose de la protection prévue et d'un droit de litige via le service client.</>,
              ]}
            />
          ),
        },
        {
          title: "Paiements",
          body: (
            <LegalList
              items={[
                <>Les paiements sont effectués via Wave, Orange Money ou carte bancaire, traités par nos prestataires de paiement.</>,
                <>Sunu Mall ne conserve pas vos données bancaires.</>,
                <>Les remboursements éligibles sont traités selon les modalités du vendeur et de la politique de la plateforme.</>,
              ]}
            />
          ),
        },
        {
          title: "Rôle des vendeurs et des livreurs",
          body: (
            <>
              <p>
                Les vendeurs s'engagent à vendre des produits licites et à respecter les{" "}
                <a href="/merchant" className="font-medium text-orange hover:underline">
                  conditions applicables à leur espace vendeur
                </a>
                . Les livreurs acceptent une vérification d'identité (KYC) et le partage de leur position pendant une course.
              </p>
              <p>
                San Sunu Mall est responsable du comportement d'un vendeur ou d'un livreur, mais s'engage à traiter tout litige
                signalé sous 48 h.
              </p>
            </>
          ),
        },
        {
          title: "Conduite interdite",
          body: (
            <LegalList
              items={[
                <>Toute vente de produits illicites, contrefaits ou dangereux.</>,
                <>Toute fraude, tentative de fraude ou abus des mécanismes de promotion.</>,
                <>Tout comportement injurieux, harcelant ou discriminatoire envers un autre utilisateur.</>,
                <>Toute tentative d'accès non autorisé aux comptes d'autrui ou aux systèmes de la plateforme.</>,
              ]}
            />
          ),
        },
        {
          title: "Litiges et droit applicable",
          body: (
            <p>
              Les présentes conditions sont soumises au droit sénégalais. En cas de désaccord, nous vous invitons à contacter notre
              service client (<span className="font-medium text-orange">support@sunumall.com</span>). À défaut de résolution
              amiable, les tribunaux de Dakar sont seuls compétents.
            </p>
          ),
        },
      ]}
    />
  );
}