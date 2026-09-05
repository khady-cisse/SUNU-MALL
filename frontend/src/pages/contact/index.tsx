import { useState } from "react";
import { ArrowRight, ChevronDown, Clock, Mail, MapPin, MessageCircle, Phone } from "lucide-react";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import { Button } from "@/components/ui/Button";

const CONTACT_CARDS = [
  { icon: Phone, title: "Téléphone", lines: ["+221 33 860 00 00", "+221 77 860 00 00"], href: "tel:+221338600000" },
  { icon: Mail, title: "Email", lines: ["support@sunumall.com", "partenariats@sunumall.com"], href: "mailto:support@sunumall.com" },
  { icon: MapPin, title: "Adresse", lines: ["Sacré-Cœur 3, Villa 123", "Dakar, Sénégal"] },
  { icon: Clock, title: "Horaires", lines: ["Lun – Sam : 8h à 20h", "Dimanche : 9h à 13h"] },
];

const FAQ = [
  {
    q: "Comment suivre ma commande ?",
    a: "Une fois votre commande en cours de livraison, ouvrez la page « Mes commandes » puis « Suivre en direct » : vous voyez le livreur se déplacer sur la carte et une estimation d'arrivée en temps réel.",
  },
  {
    q: "Que faire si ma commande arrive endommagée ?",
    a: "Prenez une photo du colis et de son contenu, puis contactez-nous sous 48h via ce formulaire ou le chat en direct. Nous ouvrons un litige et trouvons une solution rapide avec le vendeur.",
  },
  {
    q: "Comment devenir vendeur ou livreur sur Sunu Mall ?",
    a: "Vendeur : créez votre boutique depuis « Créer boutique ». Livreur : téléchargez l'application livreur, complétez votre profil et vos zones d'intervention, puis activés votre disponibilité.",
  },
  {
    q: "Quels moyens de paiement acceptez-vous ?",
    a: "Wave, Orange Money et carte bancaire (Visa/Mastercard). Paiement à la livraison selon les boutiques participantes.",
  },
];

const CONTACT_FIELDS = [
  { key: "name", label: "Votre nom", type: "text", required: true },
  { key: "email", label: "Votre email", type: "email", required: true },
  { key: "subject", label: "Sujet", type: "text", required: false },
] as const;

export default function ContactPage() {
  const [form, setForm] = useState({ name: "", email: "", subject: "", message: "" });
  const [sent, setSent] = useState(false);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const subject = encodeURIComponent(`[Contact] ${form.subject || "Demande"}`);
    const body = encodeURIComponent(`${form.name}\n${form.email}\n\n${form.message}`);
    window.location.href = `mailto:support@sunumall.com?subject=${subject}&body=${body}`;
    setSent(true);
  }

  return (
    <div className="bg-gray-50">
      {/* ─── HERO ─── */}
      <section
        style={{ background: "linear-gradient(135deg, #FFF8F0 0%, #FFF3E8 40%, #FDEEDD 100%)" }}
        className="border-b border-orange/10"
      >
        <div className="mx-auto max-w-7xl px-4 py-12 md:py-16">
          <span className="text-xs font-bold uppercase tracking-widest text-orange">On est là pour vous</span>
          <h1 className="mt-2 font-display text-3xl font-extrabold text-gray-900 md:text-4xl">Contactez Sunu Mall</h1>
          <p className="mt-3 max-w-xl text-sm leading-relaxed text-gray-500">
            Une question sur votre commande, une boutique, un litige ou un partenariat ? Notre équipe répond sous 24h ouvrées.
          </p>
        </div>
      </section>

      {/* ─── COORDONNÉES ─── */}
      <section className="mx-auto max-w-7xl px-4 py-10">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {CONTACT_CARDS.map(({ icon: Icon, title, lines, href }) => (
            <div key={title} className="rounded-2xl border border-gray-100 bg-white p-5 transition-all hover:border-orange/30 hover:shadow-md">
              <div className="grid h-11 w-11 place-items-center rounded-xl bg-orange/10">
                <Icon className="h-5 w-5 text-orange" />
              </div>
              <p className="mt-4 text-sm font-bold text-gray-800">{title}</p>
              {lines.map((line, i) =>
                href && i === 0 ? (
                  <a key={line} href={href} className="mt-1 block text-sm text-gray-500 transition-colors hover:text-orange">
                    {line}
                  </a>
                ) : (
                  <p key={line} className="mt-1 text-sm text-gray-500">
                    {line}
                  </p>
                ),
              )}
            </div>
          ))}
        </div>
      </section>

      {/* ─── FORMULAIRE + FAQ ─── */}
      <section className="mx-auto max-w-7xl px-4 pb-12">
        <div className="grid gap-6 lg:grid-cols-[1.2fr_1fr]">
          <div className="rounded-2xl border border-gray-100 bg-white p-6 md:p-8">
            <h2 className="font-display text-lg font-bold text-gray-800">Écrivez-nous</h2>
            <p className="mt-1 text-sm text-gray-400">
              Votre message sera composté dans votre messagerie (mailto) — pour un échange instantané, utilisez le chat en bas à droite.
            </p>
            <form onSubmit={handleSubmit} className="mt-6 space-y-4">
              {CONTACT_FIELDS.map(({ key, label, type, required }) => (
                <Input
                  key={key}
                  label={label}
                  type={type}
                  required={required}
                  value={form[key]}
                  onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))}
                />
              ))}
              <Textarea
                label="Message"
                value={form.message}
                onChange={(e) => setForm((f) => ({ ...f, message: e.target.value }))}
                required
              />
              <Button type="submit" loading={false}>
                Envoyer le message
              </Button>
              {sent && (
                <p className="text-sm text-success">
                  Votre messagerie s'est ouverte avec le message pré-rempli. Merci ! Nous reviendrons vers vous rapidement.
                </p>
              )}
            </form>
          </div>

          <div className="rounded-2xl border border-gray-100 bg-white p-6 md:p-8">
            <h2 className="font-display text-lg font-bold text-gray-800">Questions fréquentes</h2>
            <div className="mt-4 space-y-3">
              {FAQ.map((item) => (
                <details key={item.q} className="group rounded-xl border border-gray-100 bg-gray-50/50 p-4 [&_summary::-webkit-details-marker]:hidden">
                  <summary className="flex cursor-pointer items-center justify-between gap-3 text-sm font-semibold text-gray-700">
                    {item.q}
                    <ChevronDown className="h-4 w-4 shrink-0 text-gray-400 transition-transform group-open:rotate-180" />
                  </summary>
                  <p className="mt-2 text-sm leading-relaxed text-gray-500">{item.a}</p>
                </details>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ─── CTA CHAT ─── */}
      <section className="navy-panel">
        <div className="mx-auto flex max-w-7xl flex-col items-center justify-between gap-6 px-4 py-10 text-center md:flex-row md:text-left">
          <div className="flex items-start gap-4">
            <div className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-white/10">
              <MessageCircle className="h-5 w-5 text-orange-light" />
            </div>
            <div>
              <p className="font-display text-lg font-bold text-white">Besoin d'une réponse immédiate ?</p>
              <p className="mt-1 text-sm text-white/60">Notre assistant Sunu Mall et les conseillers répondent 7j/7.</p>
            </div>
          </div>
          <a href="#support-chat" className="btn-orange inline-flex shrink-0 items-center gap-2 rounded-xl px-6 py-3 text-sm font-bold">
            Ouvrir le chat <ArrowRight className="h-4 w-4" />
          </a>
        </div>
      </section>
    </div>
  );
}