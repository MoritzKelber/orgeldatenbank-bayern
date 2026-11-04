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

export interface Builder {
  id: number;
  name: string | null;
  biografie: string | null;
  organ_ids: number[];
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
