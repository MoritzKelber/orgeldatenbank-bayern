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
  kirche_gnd: GndMatch | null;
  adresse: Adresse;
  erhalten: boolean;
  denkmalorgel: boolean;
  prospekt_erhalten: boolean;
  bauer_name: string | null;
  bauer_id: number | null;
  bauer_confidence: BauerConfidence;
  bauer_person_id: string | null;
  jahr: Jahr;
  manuale: number | null;
  register: number | null;
  dispo: Dispo;
  bemerkung: string | null;
  memo: string | null;
  place_key: string | null;
  literatur: OrganLiteraturCitation[];
  _unclear: {
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
  beschreibung_odb: string | null;
  lebensdaten: Lebensdaten;
  beziehung: Beziehung | null;
  anmerkungen_kurz: string[];
  gnd: GndMatch | null;
}

// The Person layer, extracted from the Builder/Lemma layer at build time
// (see lib/data.ts getAllPersonen) - one entry per individual, with its
// own id ("<lemma_id>-<index>") and a back-reference to the lemma it
// came from for the surrounding prose/organ list.
export interface PersonRecord extends Person {
  id: string;
  lemma_id: number;
  lemma_name: string | null;
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

export type BmsStatus = "ok" | "unsicher" | "keine";

export interface BmsMatch {
  status: BmsStatus;
  ppn: string | null;
  url: string | null;
  matched_titel: string | null;
  matched_autor: string | null;
  matched_jahr: number | null;
  score: number | null;
  grund: string | null;
  isbn: string[];
}

export type GatewayBayernStatus = "ok" | "keine";

export interface GatewayBayernMatch {
  status: GatewayBayernStatus;
  bv_nr: string | null;
  url: string | null;
  isbn_used: string | null;
  via?: "titel";
  titel?: string | null;
}

// Frei zugängliches Digitalisat bei einem wissenschaftlichen Anbieter
// (Bibliothek, Archiv, Hochschule), ermittelt über die Deutsche Digitale
// Bibliothek und den B3Kat (etl/src/match/digitalisat_match.py).
export interface DigitalisatLink {
  url: string;
  anbieter: string;
  beschreibung: string;
  // titel = das Werk selbst, sammelband = der Band mit dem Beitrag,
  // band = der Zeitschriftenjahrgang, zeitschrift = die ganze Zeitschrift
  ebene: "titel" | "sammelband" | "band" | "zeitschrift";
  quelle: "ddb" | "b3kat";
}

export interface Digitalisat {
  status: "ok";
  links: DigitalisatLink[];
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
  bms: BmsMatch | null;
  gateway_bayern: GatewayBayernMatch | null;
  digitalisat?: Digitalisat | null;
}

// Best-effort restyling of the already-free-text BIBLIO field towards the
// citation conventions of "Die Musikforschung" (Nachname, Vorname: „Titel“,
// in: Zeitschrift Band (Jahr), S. x-y / Nachname, Vorname: „Titel“, Ort
// Jahr) - this is a display-only heuristic, not a re-parse into structured
// bibliographic metadata, so an unrecognised BIBLIO string is shown as-is
// rather than risk mangling it.
export interface BiblioFormatted {
  inPrefix: boolean;
  journal: string | null;
  rest: string;
}

const _BIBLIO_IN_PREFIX = /^in:\s*/i;
const _BIBLIO_JOURNAL = /^(.+?)\s+(?:Heft\s*)?(\d+[a-zA-Z]?)\s*,\s*(\d{3,4}(?:[/-]\d{2,4})?)\s*(?:,\s*(?:Heft\s*\d+\s*,?\s*)?S\.?\s*([\dIVXivx.\-–,\s]+))?\.?\s*$/;

// Zeitschrift/Zeitung: "Name [N.F.] Band, Jahr, Nr./H./S. ..." oder
// "Name Band (Jahr), S. ..." oder (ohne Band) "Name, Jahr, Nr./Heft ...".
// Der Name enthält keine Ziffern; so werden Orts-/Jahresangaben von
// Monografien ("München 1977 2. Aufl.") nicht für Zeitschriften gehalten.
const _BIBLIO_PERIODICAL = new RegExp(
  "^(?<name>[^\\d]+?)[\\s,]+" +
    "(?:(?:(?:Jg\\.?|Jahrgang|Jahrg\\.?|Bd\\.?)\\s*)?(?<pre>(?:Heft|H\\.)\\s*)?(?<nf>N\\.?\\s?F\\.?\\s*)?(?<vol>\\d{1,3}(?:/\\d{1,3})?[a-z]?(?:\\s*\\(\\d{1,3}\\))?)\\s*(?:,\\s*|\\s*\\(\\s*))?" +
    "(?<datum>(?:\\d{1,2}\\.\\d{1,2}\\.)?\\d{4}(?:/\\d{2,4})?)\\)?(?<tail>.*)$",
);
// Jahrbuch-/Reihenform: "Jahrbuch der bayerischen Denkmalpflege, Bd. 27 für das Jahr 1983, München 1985, S. 560 f."
const _BIBLIO_YEARBOOK = /^(?<name>[^\d,]+?),\s*(?<rest>(?:Bd\.?|Jg\.?|Jahrgang)\s*\d+(?:\/\d+)?\b.*\d{4}.*)$/;

function matchPeriodical(body: string): BiblioFormatted | null {
  const y = body.match(_BIBLIO_YEARBOOK);
  if (y?.groups) return { inPrefix: true, journal: y.groups.name.trim(), rest: y.groups.rest.trim() };

  const m = body.match(_BIBLIO_PERIODICAL);
  if (!m?.groups) return null;
  const { name: rawName, pre, nf, vol, datum, tail } = m.groups;
  const name = rawName.replace(/[\s,]+(?:vom|v\.)$/i, ""); // "Main-Post Würzburg vom 9.4.1955"
  const cleanTail = (tail ?? "").trim();
  if (/^\(\s*=/.test(cleanTail) || /\(=/.test(cleanTail)) return null; // Reihenhinweis: Monografie
  if (/^[\s,]*[A-ZÄÖÜ]/.test(cleanTail) && !/^[\s,]*(Nr|Heft|H|S)\b/.test(cleanTail)) return null; // folgt ein Ortsname o. Ä.
  const hasIssue = /\b(Nr|Heft|H)\.?\s*\d/.test(cleanTail) || /^[\s,]*S\.?\s*\d/.test(cleanTail);
  if (!vol && !/\b(Nr|Heft|H)\.?\s*\d/.test(cleanTail)) return null; // ohne Band nur mit Heft-/Nummernangabe
  if (!vol && !hasIssue) return null;
  const nfPart = nf ? "N. F. " : "";
  const dayDate = /\d\.\d/.test(datum);
  let rest: string;
  const issueM = vol?.match(/\s*\((\d{1,3})\)$/); // "9 (3), 1973" = Band 9, Heft 3
  const volNum = issueM ? vol.slice(0, issueM.index) : vol;
  if (vol) rest = `${pre ? "Heft " : ""}${nfPart}${volNum}${dayDate ? `, ${datum}` : ` (${datum})`}`;
  else rest = dayDate ? datum : `(${datum})`;
  const tailText = cleanTail.replace(/^[\s,]+/, "").replace(/\.\s*$/, ".");
  if (issueM) rest += `, H. ${issueM[1]}`;
  if (tailText) rest += `, ${tailText}`;
  return { inPrefix: true, journal: name.trim().replace(/[.,]$/, ""), rest };
}

export function formatBiblio(biblio: string | null): BiblioFormatted | null {
  if (!biblio) return null;
  const inMatch = biblio.match(_BIBLIO_IN_PREFIX);
  const body = inMatch ? biblio.slice(inMatch[0].length) : biblio;
  const periodical = matchPeriodical(body.trim());
  if (periodical) return periodical;
  if (inMatch) {
    // "in: NDB Bd.4, Berlin 1959, S. 321 f." - Sammelwerk/Nachschlagewerk kursiv, Rest unverändert
    const c = body.match(/^(?<name>[^\d,]+?)(?=\s+Bd\.?\s*\d|\s*,)(?<tail>.*)$/);
    if (c?.groups && c.groups.name.trim().length >= 2) {
      return { inPrefix: true, journal: c.groups.name.trim(), rest: c.groups.tail.replace(/^[\s,]+/, "").trim() };
    }
  }
  const journalMatch = body.match(_BIBLIO_JOURNAL);
  if (journalMatch) {
    const [, journal, band, jahr, seiten] = journalMatch;
    const rest = `${band} (${jahr})${seiten ? `, S. ${seiten.trim()}` : ""}`;
    return { inPrefix: true, journal: journal.trim(), rest };
  }
  return { inPrefix: inMatch !== null, journal: null, rest: body.trim() };
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
