import { LegalLayout, LegalList } from "./LegalLayout";

export default function PolitiqueConfidentialitePage() {
  return (
    <LegalLayout
      badge="Politique de confidentialité"
      title="Politique de confidentialité"
      intro="Comment Sunu Mall collecte, utilise et protège vos données personnelles lorsque vous utilisez la plateforme, en conformité avec la loi sénégalaise n° 2008-12 du 25 janvier 2008 sur la protection des données à caractère personnel."
      updatedAt="6 septembre 2026"
      sections={[
        {
          title: "Données que nous collectons",
          body: (
            <>
              <p>Nous collectons uniquement les données nécessaires au fonctionnement du service :</p>
              <LegalList
                items={[
                  <>
                    <strong>Compte :</strong> nom, prénom, email, téléphone, adresses de livraison.
                  </>,
                  <>
                    <strong>Commandes :</strong> historique d'achats, montants, préférences de livraison, interactions avec les
                    boutiques.
                  </>,
                  <>
                    <strong>Paiements :</strong> les moyens de paiement (Wave, Orange Money, carte) sont traités par nos
                    prestataires ; Sunu Mall ne stocke jamais vos données de carte bancaire.
                  </>,
                  <>
                    <strong>Livreurs :</strong> pièces d'identité, zones d'intervention et position GPS pendant les courses
                    (nécessaire au suivi en temps réel de votre commande).
                  </>,
                  <>
                    <strong>Navigation :</strong> cookies et jetons de session pour sécuriser votre connexion et améliorer
                    l'expérience.
                  </>,
                ]}
              />
            </>
          ),
        },
        {
          title: "Utilisation de vos données",
          body: (
            <LegalList
              items={[
                <>Exécution de vos commandes : transmission à la boutique et au livreur concerné.</>,
                <>Suivi de livraison et notifications (email, dans l'application) relatives à vos commandes.</>,
                <>Prévention de la fraude et vérification d'identité (KYC des vendeurs et livreurs).</>,
                <>Amélioration de la plateforme, statistiques anonymisées et support client.</>,
                <>Respect de nos obligations légales et de la facturation.</>,
              ]}
            />
          ),
        },
        {
          title: "Partage et sous-traitance",
          body: (
            <LegalList
              items={[
                <>
                  <strong>Boutiques vendeuses</strong> reçoivent les informations nécessaires à la préparation de votre commande
                  (produits, adresse de livraison).
                </>,
                <>
                  <strong>Livreurs affectés</strong> à votre course voient votre nom et votre adresse de livraison pendant la
                  livraison uniquement.
                </>,
                <>
                  <strong>Prestataires de paiement</strong> (Wave, Orange Money, émetteurs de cartes) traitent les transactions ;
                  nous les sélectionnons pour leur conformité en matière de sécurité des données.
                </>,
                <>
                  Nous ne vendons jamais vos données personnelles à des tiers.
                </>,
              ]}
            />
          ),
        },
        {
          title: "Durée de conservation",
          body: (
            <LegalList
              items={[
                <>
                  Les données de compte sont conservées tant que votre compte reste actif, et au maximum 12 mois après sa
                  suppression pour les obligations légales restantes.
                </>,
                <>
                  Les données de commande et de facturation sont conservées conformément aux obligations comptables (5 ans).
                </>,
                <>
                  Les positions GPS des courses sont conservées 90 jours, durée nécessaire au suivi et au traitement d'éventuels
                  litiges.
                </>,
              ]}
            />
          ),
        },
        {
          title: "Vos droits",
          body: (
            <>
              <p>Conformément à la loi 2008-12, vous bénéficiez, sur simple demande, des droits suivants :</p>
              <LegalList
                items={[
                  <>Droit d'accès aux données vous concernant.</>,
                  <>Droit de rectification de données inexactes ou incomplètes.</>,
                  <>Droit à l'effacement lorsque les données ne sont plus nécessaires.</>,
                  <>Droit d'opposition au traitement ou à la désinscription des communications marketing.</>,
                ]}
              />
              <p>
                Pour exercer ces droits, écrivez-nous à{" "}
                <span className="font-medium text-orange">support@sunumall.com</span> ou par courrier (NEJ digital, Sacré-Cœur 3,
                Villa 123, Dakar). Nous répondons sous 30 jours.
              </p>
            </>
          ),
        },
        {
          title: "Sécurité",
          body: (
            <LegalList
              items={[
                <>Transmission chiffrée (HTTPS) de toutes les données entre votre navigateur et nos serveurs.</>,
                <>Mots de passe stockés de façon irréversible (hachés) ; codes de confirmation à usage unique et limités dans le temps.</>,
                <>Accès strict aux données selon le rôle (client, vendeur, livreur, admin) et journalisation des accès sensibles.</>,
                <>Sauvegardes régulières et surveillance des incidents de sécurité.</>,
              ]}
            />
          ),
        },
        {
          title: "Cookies et traceurs",
          body: (
            <p>
              Sunu Mall utilise des cookies strictement nécessaires (session, préférences) et des cookies d'analyse anonymisés pour
              mesurer la fréquentation. Aucun cookie publicitaire tiers n'est déposé sans votre consentement. Vous pouvez configurer
              votre navigateur à tout moment ; certaines fonctionnalités (connexion, panier) pourraient alors être indisponibles.
            </p>
          ),
        },
        {
          title: "Contact délégué à la protection des données",
          body: (
            <p>
              Pour toute question relative au traitement de vos données personnelles, contactez notre référent :{" "}
              <span className="font-medium text-orange">dpo@sunumall.com</span>. En cas de désaccord persistant, vous pouvez saisir
              la Commission des Données Personnelles (CDP du Sénégal).
            </p>
          ),
        },
      ]}
    />
  );
}