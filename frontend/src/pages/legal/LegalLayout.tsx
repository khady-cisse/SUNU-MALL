import { type ReactNode } from "react";
import { Scale } from "lucide-react";

export interface LegalSection {
  title: string;
  body: ReactNode;
}

interface LegalLayoutProps {
  badge: string;
  title: string;
  intro: string;
  /** Dernière mise à jour affichée sous l'intro. */
  updatedAt: string;
  sections: LegalSection[];
}

export function LegalLayout({ badge, title, intro, updatedAt, sections }: LegalLayoutProps) {
  return (
    <div className="bg-gray-50">
      <section
        style={{ background: "linear-gradient(135deg, #FFF8F0 0%, #FFF3E8 40%, #FDEEDD 100%)" }}
        className="border-b border-orange/10"
      >
        <div className="mx-auto max-w-3xl px-4 py-12 md:py-16">
          <span className="flex items-center gap-2 text-xs font-bold uppercase tracking-widest text-orange">
            <Scale className="h-4 w-4" /> {badge}
          </span>
          <h1 className="mt-2 font-display text-3xl font-extrabold text-gray-900 md:text-4xl">{title}</h1>
          <div>
            <p className="mt-3 text-sm leading-relaxed text-gray-500">{intro}</p>
            <p className="mt-2 text-xs font-medium text-gray-400">Dernière mise à jour : {updatedAt}</p>
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-3xl px-4 py-10">
        <div className="space-y-6">
          {sections.map((section) => (
            <div key={section.title} className="rounded-2xl border border-gray-100 bg-white p-6 md:p-7">
              <h2 className="font-display text-lg font-bold text-gray-800">{section.title}</h2>
              <div className="mt-3 space-y-3 text-sm leading-relaxed text-gray-600">{section.body}</div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

/** Paragraphe, liste à puces ou énumération numérotée pour les pages légales. */
export function LegalList({ items, ordered = false }: { items: ReactNode[]; ordered?: boolean }) {
  const className = "ml-5 space-y-1.5 list-disc marker:text-orange";
  const Tag = ordered ? "ol" : "ul";
  return (
    <Tag className={ordered ? "ml-5 list-decimal space-y-1.5 marker:text-orange" : className}>
      {items.map((item, i) => (
        <li key={i}>{item}</li>
      ))}
    </Tag>
  );
}