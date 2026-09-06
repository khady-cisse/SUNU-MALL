import { LegalLayout, LegalList } from "./LegalLayout";

export default function MentionsLegalesPage() {
  return (
    <LegalLayout
      badge="Mentions légales"
      title="Mentions légales"
      intro="Les informations relatives à l'identification de l'éditeur et de l'hébergeur de la plateforme Sunu Mall, conformément à la réglementation en vigueur au Sénégal."
      updatedAt="6 septembre 2026"
      sections={[
        {
          title: "Éditeur de la plateforme",
          body: (
            <>
              <p>
                La plateforme <strong>Sunu Mall</strong> est éditée par la société <strong>NEJ digital</strong>, immatriculée
                au Registre du Commerce et du Crédit Mobilier de Dakar.
              </p>
              <LegalList
                ordered
                items={[
                  <>
                    Siège social : Sacré-Cœur 3, Villa 123, Dakar, Sénégal.
                  </>,
                  <>
                    Adresse email : <span className="font-medium text-orange">support@sunumall.com</span>
                  </>,
                  <>Téléphone : +221 33 860 00 00 / +221 77 860 00 00</>,
                ]}
              />
            </>
          ),
        },
        {
          title: "Directeur de la publication",
          body: (
            <p>
              Le directeur de la publication est le président de <strong>NEJ digital</strong>. Il est joignable à l'adresse
              électronique <span className="font-medium text-orange">partenariats@sunumall.com</span> pour toute demande
              relative au contenu publié sur la plateforme.
            </p>
          ),
        },
        {
          title: "Hébergement",
          body: (
            <LegalList
              items={[
                <>Le site est hébergé dans un datacenter sécurisé fournissant redondance réseau et sauvegardes régulières.</>,
                <>
                  Les données stockées (comptes, commandes, paiements) sont hébergées en conformité avec les règles applicables
                  au traitement des données au Sénégal. Le détail figure dans la{" "}
                  <a href="/politique-de-confidentialite" className="font-medium text-orange hover:underline">
                    politique de confidentialité
                  </a>
                  .
                </>,
              ]}
            />
          ),
        },
        {
          title: "Propriété intellectuelle",
          body: (
            <>
              <p>
                La structure générale, les textes, logos, marques, visuels et éléments graphiques de Sunu Mall sont la propriété
                de <strong>NEJ digital</strong> ou de ses partenaires, et sont protégés par le droit de la propriété
                intellectuelle.
              </p>
              <p>
                Toute reproduction, représentation ou diffusion sans autorisation écrite préalable est interdite. Les boutiques et
                descriptions de produits demeurent la propriété de leurs vendeurs respectifs.
              </p>
            </>
          ),
        },
        {
          title: "Responsabilité",
          body: (
            <LegalList
              items={[
                <>Sunu Mall agit comme place de marché mettant en relation vendeurs, livreurs et clients.</>,
                <>
                  La plateforme ne saurait être tenue responsable des conséquences d'un usage frauduleux de la plateforme, ou d'une
                  utilisation du site contraire aux{" "}
                  <a href="/conditions-utilisation" className="font-medium text-orange hover:underline">
                    conditions d'utilisation
                  </a>
                  .
                </>,
                <>
                  En cas de litige, le client peut contacter le service client, détailler sa demande et saisir, le cas échéant, la
                  juridiction compétente de Dakar.
                </>,
              ]}
            />
          ),
        },
      ]}
    />
  );
}