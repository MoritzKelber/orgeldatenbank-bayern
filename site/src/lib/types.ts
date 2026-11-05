// Mirrors the JSON shape written by etl/src/pipeline.py - keep in sync.

export type JahrQualifier = "exakt" | "vor" | "nach" | "um" | "bereich" | "unbekannt" | "fehlt";

export interface Jahr {
  jahr_raw: string | null;
  jahr: number | null;
  jahr_bis: number | null;
  qualifier: JahrQualifier;
}

export interface DispoSection {
  name: string;
  qualifier: string | null;
  items: string[];
}

export interface Dispo {
  raw: string | null;
  parsed: boolean;
  sections: DispoSection[];
  koppeln: string[];
  bemerkungen: string | null;
  quelle: string | null;
  extra_notes: string[];
}

export type LiteraturConfidence = "exact" | "normalisiert" | "fuzzy" | "keine";

export interface OrganLiteraturCitation {
  lit: string | null;
  disp: boolean;
  abb: boolean;
  kurztitel: string | null;
  confidence: LiteraturConfidence;
  slug: string | null;
}

export interface Adresse {
  zeile1: string | null;
  zeile2: string | null;
  plz: string | null;
  ort: string | null;
}

export type BauerConfidence = "exact" | "none";

export interface Organ {
  id: number;
  ort: string | null;
  gemeinde: string | null;
  landkreis: string | null;
  regierungsbezirk: string | null;
  kirche: string | null;
  adresse: Adresse;
  erhalten: boolean;
  denkmalorgel: boolean;
  bauer_name: string | null;
  bauer_id: number | null;
  bauer_confidence: BauerConfidence;
  jahr: Jahr;
  manuale: number | null;
  register: number | null;
  dispo: Dispo;
  bemerkung: string | null;
  memo: string | null;
  place_key: string | null;
  literatur: OrganLiteraturCitation[];
  _unclear: {
    dp: boolean;
    kl: string | null;
    t: string | null;
    satz: number | null;
    rbz_raw_unrecognized: string | null;
  };
}

export interface OrganIndexEntry {
  id: number;
  ort: string | null;
  kirche: string | null;
  gemeinde: string | null;
  landkreis: string | null;
  regierungsbezirk: string | null;
  bauer_name: string | null;
  manuale: number | null;
  register: number | null;
  erhalten: boolean;
  denkmalorgel: boolean;
  jahr: number | null;
  jahr_anzeige: string | null;
}

export interface Lebensdaten {
  raw: string[];
  geburtsjahr: number | null;
  todesjahr: number | null;
}

export interface Beziehung {
  typ: string;
  bezug_index: number;
}

export type GndStatus = "ok" | "unsicher" | "keine" | "nicht_zutreffend";

export interface GndMatch {
  status: GndStatus;
  gnd_id: string | null;
  url: string | null;
  preferred_name: string | null;
  geburtsjahr: number | null;
  todesjahr: number | null;
  name_score: number | null;
  candidates_considered: number;
  grund: string | null;
}

export interface Person {
  index: number;
  name_raw: string;
  nachname: string | null;
  vorname: string | null;
  namenszusatz: string | null;
  lebensdaten: Lebensdaten;
  beziehung: Beziehung | null;
  anmerkungen_kurz: string[];
  gnd: GndMatch | null;
}

export interface Builder {
  id: number;
  name: string | null;
  biografie: string | null;
  personen: Person[];
  organ_ids: number[];
}

export const BEZIEHUNG_LABELS: Record<string, string> = {
  sohn: "Sohn von",
  tochter: "Tochter von",
  vater: "Vater von",
  mutter: "Mutter von",
  bruder: "Bruder von",
  schwester: "Schwester von",
  enkel: "Enkel von",
  neffe: "Neffe von",
};

export function personDisplayName(p: Person): string {
  const parts = [p.vorname, p.nachname].filter(Boolean);
  let name = parts.length ? parts.join(" ") : p.name_raw;
  if (p.namenszusatz) name += ` ${p.namenszusatz}`;
  return name;
}

export function personLebensdaten(p: Person): string | null {
  if (p.gnd?.status === "ok" && (p.gnd.geburtsjahr != null || p.gnd.todesjahr != null)) {
    return `${p.gnd.geburtsjahr ?? "?"}–${p.gnd.todesjahr ?? "?"}`;
  }
  const g = p.lebensdaten;
  if (g.geburtsjahr != null && g.todesjahr != null) return `${g.geburtsjahr}–${g.todesjahr}`;
  if (g.geburtsjahr != null) return `* ${g.geburtsjahr}`;
  if (g.todesjahr != null) return `† ${g.todesjahr}`;
  if (g.raw.length) return g.raw.join("; ");
  return null;
}

export interface LiteraturKeyword {
  stichwort: string | null;
  bemerkung: string | null;
}

export interface LiteraturEntry {
  slug: string;
  kurztitel: string;
  autor: string | null;
  titel: string | null;
  biblio: string | null;
  vorhanden: string | null;
  abstract: string | null;
  keywords: LiteraturKeyword[];
  organ_ids: number[];
}

export function formatCount(n: number | null): string | null {
  if (n == null) return null;
  return n === 0 ? "–" : String(n);
}

export function formatJahr(jahr: Jahr): string | null {
  switch (jahr.qualifier) {
    case "exakt":
      return jahr.jahr != null ? String(jahr.jahr) : null;
    case "vor":
      return jahr.jahr != null ? `vor ${jahr.jahr}` : null;
    case "nach":
      return jahr.jahr != null ? `nach ${jahr.jahr}` : null;
    case "um":
      return jahr.jahr != null ? `um ${jahr.jahr}` : null;
    case "bereich":
      return jahr.jahr != null ? `${jahr.jahr}–${jahr.jahr_bis}` : null;
    case "unbekannt":
      return jahr.jahr_raw ? `unbekannt (${jahr.jahr_raw})` : "unbekannt";
    case "fehlt":
      return null;
    default:
      return null;
  }
}

export const RBZ_LABELS: Record<string, string> = {
  OB: "Oberbayern",
  NB: "Niederbayern",
  OPf: "Oberpfalz",
  OFr: "Oberfranken",
  MFr: "Mittelfranken",
  UFr: "Unterfranken",
  Schw: "Schwaben",
};
