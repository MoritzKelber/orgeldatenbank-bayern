// Formt einen Literatureintrag (Autor, Titel, freier BIBLIO-Text) in ein
// Zitat nach den „Hinweisen für Autor:innen“ der Zeitschrift *Die
// Musikforschung* (musikforschung.de/richtlinien, Punkt 6) um – in der Form
// eines Literaturverzeichnisses, also mit „Nachname, Vorname“:
//
//   Monografie:    Nachname, Vorname, *Titel. Untertitel* (= Reihe 12), Ort Jahr.
//   Aufsatz:       Nachname, Vorname, „Titel“, in: *Zeitschrift* 38 (1981), S. 57–75.
//   Sammelband:    Nachname, Vorname, „Titel“, in: *Sammelband*, hrsg. von Vorname
//                  Nachname, Ort Jahr, S. 248–256.
//   Herausgeber:   Nachname, Vorname (Hrsg.), *Titel*, Ort Jahr.
//   Anonymus:      Anon., „Titel“, in: …
//
// Nach dem Namen steht ein Komma (kein Doppelpunkt); Aufsatz- und Beitrags-
// titel in doppelten typographischen Anführungszeichen, darin enthaltene
// Anführungszeichen als einfache; selbständige Titel kursiv; Seiten mit
// „S.“, Bereiche mit Gedankenstrich, „f.“/„ff.“ mit Leerzeichen; Reihen in
// Klammern mit „=“ vor der Ortsangabe; Auflage als Hochzahl vor dem Jahr;
// mehrere Verlagsorte mit Schrägstrich.
//
// Die Ausgangsdaten sind Freitext; alles hier ist eine Darstellungsheuristik.
// Wo ein BIBLIO-String keinem bekannten Muster entspricht, wird er bereinigt,
// aber strukturell unverändert übernommen.

export type ZitatArt = "monografie" | "zeitschrift" | "sammelband" | "unselbstaendig";

export interface Zitat {
  art: ZitatArt;
  autor: string | null;        // "Fischer, Hermann / Wohnhaas, Theodor" | "Anon." | "Hennecke, Gert (Hrsg.)"
  titel: string;               // bereinigter Titel
  unselbstaendig: boolean;     // true -> „Titel“, in: …;  false -> *Titel*
  container: string | null;    // kursiv gesetzter Zeitschriften-/Sammelbandtitel (nur bei unselbstaendig)
  rest: string;                // alles nach dem Container bzw. nach dem Titel (Ort Jahr, Seiten …), ohne Schlusspunkt
}

const MONTHS = "Jan(?:uar)?|Feb(?:ruar)?|März|Maerz|Apr(?:il)?|Mai|Juni?|Juli?|Aug(?:ust)?|Sept?(?:ember)?|Okt(?:ober)?|Nov(?:ember)?|Dez(?:ember)?";
const DATUM = `(?:(?:\\d{1,2}\\.\\s?\\d{1,2}\\.\\s?)|(?:(?:${MONTHS})\\.?(?:/(?:${MONTHS})\\.?)?\\s+))?\\d{4}(?:/\\d{2,4})?`;
const NOT_PLACE = new RegExp(`^(?:${MONTHS}|Jahre?n?|Jahrg(?:ang)?\\.?|Bd\\.?|Band|Nr\\.?|Heft|H\\.|Teil|Tl\\.?|Jg\\.?|S\\.|vom|am|bis|seit|um|ca\\.?|Anno)$`, "i");

// --- Seiten, Striche, Abkürzungen -------------------------------------------------

export function tidyPages(s: string): string {
  return s
    .replace(/\r?\n/g, " ")
    .replace(/\bS\.\s*(?=\d|[IVX])/g, "S. ")
    .replace(/\bSp\.\s*(?=\d)/g, "Sp. ")
    .replace(/\b(Nr|Bd|H|Hft|Jg|Tl|Teil)\.\s*(?=\d)/g, "$1. ")
    .replace(/\bHeft\s*(?=\d)/g, "Heft ")
    .replace(/(\d)\s*-\s*(\d)/g, "$1–$2")              // Seiten-/Nummernbereiche: Gedankenstrich
    .replace(/(\d)\s?(ff?)\.?(?=[\s,;)]|$)/g, "$1 $2.")  // 37f. / 37 ff -> 37 f. / 37 ff.
    .replace(/(\d),(?=\d)/g, "$1, ")
    .replace(/\bu\.\s?a\./g, "u. a.")
    .replace(/\bo\.\s?J\./g, "o. J.")
    .replace(/\bo\.\s?O\./g, "o. O.")
    .replace(/\busw\./g, "u. a.")
    .replace(/\bhrsg\.\s*v\.\s/g, "hrsg. von ")
    .replace(/\b(?:hg|Hg)\.\s*(?:v\.|von|vom)?\s*/g, "hrsg. von ")
    .replace(/\bHrsg\.\s+(?=[A-ZÄÖÜa-z])/g, "hrsg. von ")
    .replace(/\bhrsg\.\s+(?=[A-ZÄÖÜ])/g, "hrsg. von ")
    .replace(/\bhrsg\. von (?:von|vom)\b/g, "hrsg. von")
    .replace(/\s+,/g, ",")
    .replace(/,\s*,/g, ",")
    .replace(/\s{2,}/g, " ")
    .trim();
}

const CITIES = new Set(["München", "Zürich", "Kassel", "Basel", "Tours", "London", "Stuttgart", "Weimar", "Wolfenbüttel",
  "Salzburg", "Berlin", "Wien", "Regensburg", "Frankfurt", "Mainz", "Leipzig", "Wiesbaden", "Tutzing", "Laaber", "Hildesheim",
  "Paris", "Köln", "Bonn", "Freiburg", "Augsburg", "Nürnberg", "Würzburg", "Passau", "Bamberg", "Innsbruck", "Graz", "Linz",
  "New York", "Hamburg", "Dresden", "Darmstadt", "Göttingen", "Heidelberg", "Tübingen", "Karlsruhe", "Ulm"]);
const SUP = "⁰¹²³⁴⁵⁶⁷⁸⁹";
const toSup = (n: string) => n.split("").map((d) => SUP[Number(d)]).join("");

function tidyPlaces(s: string): string {
  // "München-Zürich 1981" -> "München/Zürich 1981" (nur bei bekannten Verlagsorten)
  s = s.replace(/\b([A-ZÄÖÜ][a-zäöüß]+(?:-[A-ZÄÖÜ][a-zäöüß]+)+)(?=\s+(?:[\d⁰-⁹]|o\. J\.))/g, (m) => {
    const parts = m.split("-");
    return parts.every((p) => CITIES.has(p)) ? parts.join("/") : m;
  });
  s = s.replace(/\bFrankfurt a\.\s?M\./g, "Frankfurt am Main").replace(/\bFrankfurt\/M\./g, "Frankfurt am Main");
  // Auflage als Hochzahl: "München 1977 2. Aufl." / "München 1984 (9.Aufl.)" -> "München ⁹1984"
  s = s.replace(/(\d{4})\s*[,(]?\s*(\d{1,2})\.,?\s*(?:[a-zäöü.]+\s+)*Aufl(?:age)?\.?\)?/g, (_m, jahr, n) => `${toSup(n)}${jahr}`);
  s = s.replace(/^(\d{1,2})\.,?\s*(?:[a-zäöü.]+\s+)*Aufl(?:age)?\.?\s+([A-ZÄÖÜ][^\d,]*?\s)(\d{4})/g, (_m, n, pre, jahr) => `${pre}${toSup(n)}${jahr}`);
  return s;
}

// --- Autor -----------------------------------------------------------------------

export function tidyAutor(autor: string | null): string | null {
  if (!autor) return null;
  let a = autor.replace(/\r?\n/g, " ").trim().replace(/\s+/g, " ");
  const half = Math.floor(a.length / 2);
  if (a.length > 6 && a.slice(0, half).trim() === a.slice(half).trim()) a = a.slice(0, half).trim(); // doppelt erfasst
  if (/^anonym/i.test(a)) return "Anon.";
  a = a.replace(/\s*\/\s*/g, " / ").replace(/\s*;\s*/g, " / ");
  // "Fischer, Hermann und Wohnhaas, Theodor" -> "Fischer, Hermann / Wohnhaas, Theodor"
  a = a.replace(/(, [^,/]+?) und (?=[A-ZÄÖÜ][^,/]+, )/g, "$1 / ");
  a = a.replace(/\bu\.\s?a\./g, "u. a.").replace(/\((hrsg|hg)\.?\)/gi, "(Hrsg.)").replace(/\s*\(Hrsg\.\)/g, " (Hrsg.)");
  return a.replace(/,\s*$/, "");
}

// --- Titel -----------------------------------------------------------------------

export function tidyTitel(titel: string, inQuotes: boolean): string {
  let t = titel.trim().replace(/\s+/g, " ").replace(/\.{2,}/g, "…").replace(/\.\s*$/, "");
  // Untertitel: " - Untertitel" -> ". Untertitel" (Großbuchstabe) bzw. " – " (sonst)
  t = t.replace(/\s+-\s+(?=[A-ZÄÖÜ„])/g, ". ").replace(/\s+-\s+/g, " – ");
  t = t.replace(/"([^"]*)"/g, "„$1“");                 // gerade -> typographische Anführungszeichen
  if (inQuotes) t = t.replace(/„/g, "‚").replace(/“/g, "‘"); // innerhalb von „…“ nur einfache
  return t;
}

function tidyContainer(c: string): string {
  let t = c.trim().replace(/[,.]$/, "").replace(/^FS(?= )/, "Festschrift").replace(/\.{3}/g, "…");
  t = t.replace(/\s+-\s+(?=[A-ZÄÖÜ„])/g, ". ").replace(/\s+-\s+/g, " – ");
  return t.replace(/"([^"]*)"/g, "„$1“");
}

// --- Zeitschriften --------------------------------------------------------------

const PERIODICAL = new RegExp(
  "^(?<name>[^\\d]+?)[\\s,]*" +
    "(?:(?:(?:Jg\\.?|Jahrgang|Jahrg\\.?|Bd\\.?)\\s*)?(?<pre>(?:Heft|H\\.|Nr\\.?)\\s*)?(?<nf>N\\.?\\s?F\\.?\\s*)?" +
    "(?<vol>\\d{1,3}(?:/\\d{1,3})?[a-z]?)" +
    "(?:\\s*\\((?<heft1>\\d{1,3})\\)|[\\s,/]*(?:Nr\\.?|H\\.|Heft)\\s*(?<heft2>\\d{1,3}(?:/\\d{1,3})?))?" +
    "\\s*(?:,\\s*|\\s*\\(\\s*))?" +
    `(?<datum>${DATUM})\\)?(?<tail>.*)$`,
);
const YEARBOOK = /^(?<name>[^\d,]+?),\s*Bd\.?\s*(?<vol>\d+(?:\/\d+)?)\s+für (?:das|die) Jahre?\s+(?<jahr>\d{4}(?:\/\d{2,4})?),\s*(?<rest>.*)$/;

function periodical(body: string): { container: string; rest: string } | null {
  const y = body.match(YEARBOOK);
  if (y?.groups) return { container: y.groups.name.trim(), rest: `${y.groups.vol} (${y.groups.jahr}), ${y.groups.rest.trim()}` };

  const m = body.match(PERIODICAL);
  if (!m?.groups) return null;
  const { pre, nf, vol, heft1, heft2, datum, tail } = m.groups;
  const name = m.groups.name.replace(/[\s,]+(?:vom|v\.)$/i, "").trim().replace(/[.,]$/, "");
  if (!name || /\b(?:hrsg\. von|S\.)$/.test(name)) return null;
  const cleanTail = (tail ?? "").trim().replace(/^[.,;\s]+/, "");
  if (/^[A-ZÄÖÜ]/.test(cleanTail) && !/^(Nr|Heft|H|S|Sp)\b/.test(cleanTail)) return null; // Ortsname o. Ä. folgt
  // ohne Bandzahl nur, wenn eine Heft-/Nummernangabe vorliegt ("Orgel International, 1998, Heft 3")
  if (!vol && !pre && !/^(Nr|Heft|H)\.?\s*\d/.test(cleanTail)) return null;

  let tailText = cleanTail;
  let heft = heft1 ?? heft2 ?? null;
  const hm = tailText.match(/^(?:Heft|H\.)\s*(\d{1,3}(?:\/\d{1,3})?)\s*,?\s*/);
  if (!heft && hm && !pre && vol) { heft = hm[1]; tailText = tailText.slice(hm[0].length); }

  let rest: string;
  if (pre) rest = `(${datum}), ${/^Nr/.test(pre) ? "Nr." : "H."} ${vol}`;
  else if (!vol) rest = `(${datum})`;
  else rest = `${nf ? "N. F. " : ""}${vol}${heft ? `/${heft}` : ""} (${datum})`;
  if (tailText) rest += `, ${tailText}`;
  return { container: name, rest };
}

// --- Ort Jahr ---------------------------------------------------------------------

const PLACE_YEAR = /(?:^|[,.;]\s*)(?<ort>o\. O\.|[A-ZÄÖÜ][\wäöüß.\-/]*(?:\s[A-ZÄÖÜa-z][\wäöüß.\-/]*){0,3}?)\s+(?<jahr>o\. J\.|[⁰-⁹]*\d{4}(?:\/\d{1,4})?(?:\s*ff\.)?)(?=\s*[,;(.]|\s*$)/g;

function lastPlaceYear(head: string): { index: number; length: number; ort: string; jahr: string } | null {
  let found = null;
  for (const m of head.matchAll(PLACE_YEAR)) {
    const ort = m.groups!.ort.trim();
    const lastWord = ort.split(/\s/).pop() ?? "";
    if (NOT_PLACE.test(lastWord) || NOT_PLACE.test(ort)) continue;
    const yr = Number(m.groups!.jahr.replace(/[^\d].*$/, "").replace(/^[⁰-⁹]+/, ""));
    if (yr && (yr < 1450 || yr > 2100)) continue;
    const lead = m[0].length - (m[0].trimStart().length) + (m[0].match(/^[,.;]\s*/)?.[0].length ?? 0);
    found = { index: m.index! + lead, length: m[0].length - lead, ort, jahr: m.groups!.jahr };
  }
  return found;
}

// --- Sammelbände ----------------------------------------------------------------

function namesToNatural(eds: string): string {
  // "Klais, Hans Gerd" -> "Hans Gerd Klais"; "Aegidius Kolb / Ewald Kohler" -> "Aegidius Kolb und Ewald Kohler"
  const parts = eds.split(/\s*\/\s*|\s*;\s*/).map((p) => {
    const m = p.match(/^([^,]+),\s*(.+)$/);
    return m ? `${m[2].trim()} ${m[1].trim()}` : p.trim();
  });
  if (parts.length === 1) return parts[0];
  if (parts.length === 2) return `${parts[0]} und ${parts[1]}`;
  return `${parts[0]} u. a.`;
}

function collection(body: string): { container: string; rest: string; bareNumber: boolean } | null {
  let b = body;
  let editors: string | null = null;

  // Herausgeber vorangestellt: "Klais, Hans Gerd (Hrsg.), Titel, Ort Jahr, S. …" / "A / B (Hrsg.): Titel …"
  const edFirst = b.match(/^(?<eds>[^()]+?)\s*\((?:Hrsg|Hg)\.?\)\s*[:,]\s*(?<rest>.+)$/);
  if (edFirst?.groups) { editors = namesToNatural(edFirst.groups.eds); b = edFirst.groups.rest; }

  // Herausgeber nachgestellt: "Titel, hrsg. von X, Ort Jahr, S. …" / "Titel. Hrsg. X. Ort Jahr"
  const edTail = b.match(/^(?<title>.+?)[.,]?\s*hrsg\. von\s+(?<eds>.+?)(?=[.,]\s*(?:(?:o\. O\.|[A-ZÄÖÜ][^,.]*?)\s(?:[⁰-⁹]*\d{4}|o\. J\.)|\(=|S\.\s?\d)|$)(?<after>.*)$/);
  if (edTail?.groups && edTail.groups.title.trim()) { editors = editors ?? edTail.groups.eds.trim(); b = edTail.groups.title + edTail.groups.after; }

  const pages = b.match(/[,.]?\s*(S\.\s?[\dIVX].*)$/);
  const pagesText = pages ? pages[1] : "";
  const head = pages ? b.slice(0, pages.index) : b;

  const py = lastPlaceYear(head);
  let title: string;
  let placeYear = "";
  let between = "";
  if (py) {
    title = head.slice(0, py.index).trim().replace(/[,.]$/, "");
    placeYear = `${py.ort} ${py.jahr}`;
    between = head.slice(py.index + py.length).trim().replace(/^[,;.]\s*/, "");
  } else {
    title = head.trim().replace(/[,.]$/, "");
  }
  if (!title) return null;
  // "Titel, Bd. 2" -> Bandangabe hinter den Titel
  let band = "";
  const bm = title.match(/^(.*?[^\d,]),?\s*(Bd\.?\s*\d+(?:,\s*Teil\s*\d+)?|Band\s+\d+(?:,\s*Teil\s*\d+)?|\d{1,3}(?:\/\d{1,3})?)$/);
  if (bm && bm[1].trim()) {
    title = bm[1].trim().replace(/[,.]$/, "");
    band = /^\d/.test(bm[2]) ? bm[2] : bm[2].replace(/^Band\s+/, "Bd. ").replace(/Bd\.?\s*/, "Bd. ");
  }
  // Reihe "(= …)" aus Zwischenteil/Seitenteil vor den Ort ziehen
  let series = "";
  let pagesClean = pagesText;
  const sm = (between + " " + pagesText).match(/\(=\s*([^)]+)\)/);
  if (sm) {
    series = ` (= ${sm[1].replace(/\bBd\.?\s*/g, "").trim()})`;
    between = between.replace(sm[0], "").trim();
    pagesClean = pagesText.replace(sm[0], "").trim();
  }
  // Reihe in runden Klammern am Titelende: "Heilig-Kreuz-Kirche Landsberg (Große Kunstführer 144)"
  const tm = title.match(/^(.*?)\s*\(([^()]*\d[^()]*)\)$/);
  if (tm && !series && /Kunstführer|Reihe|Schriften|Beiträge|Hefte?|Bd\.|Band|Nr\./.test(tm[2])) { title = tm[1]; series = ` (= ${tm[2].replace(/\bBd\.?\s*/g, "").trim()})`; }

  const restParts = [band, editors ? `hrsg. von ${editors}` : "", between.replace(/\(=\s*[^)]+\)/, "").trim()].filter(Boolean);
  let rest = restParts.join(", ");
  if (placeYear) rest = (rest ? `${rest}${series}, ` : series ? `${series.trim()}, ` : "") + placeYear;
  else if (series) rest = rest ? `${rest}${series}` : series.trim();
  if (pagesClean) rest = rest ? `${rest}, ${pagesClean}` : pagesClean;
  return {
    container: tidyContainer(title),
    rest: rest.replace(/,\s*,/g, ",").replace(/\s+,/g, ",").replace(/,\s*\./g, ".").trim(),
    bareNumber: /^\d/.test(band), // "*Fränkische Lebensbilder* 7, Neustadt 1977": Zahl ohne Komma an den Titel
  };
}

// --- Monografie: Reihenangabe ----------------------------------------------------

const SERIES_WORDS = /Beiträge|Schriften|Studien|Veröffentlichungen|Reihe|Kunstführer|Hefte?|Dokumente|Documenta|Arbeitsheft|Arbeitsblätter|Neujahrsblatt|Kunstdenkmale|Kunstdenkmäler|Blätter|Jahrbuch|Bd\.|Band|Nr\./;

function monograph(body: string): string {
  // "(= Reihe)" ans Ende gestellt -> vor die Ortsangabe
  const sm = body.match(/^(.*?)\s*\(=\s*([^)]+)\)\s*$/);
  if (sm) return `(= ${sm[2].replace(/\bBd\.?\s*/g, "").trim()}), ${sm[1].trim().replace(/[,.]$/, "")}`;
  // "Reihe Bd. 3, Ort Jahr" -> "(= Reihe 3), Ort Jahr"
  const py = lastPlaceYear(body);
  if (py && py.index > 0) {
    const pre = body.slice(0, py.index).trim().replace(/[,.]$/, "");
    const after = body.slice(py.index);
    if (pre && !/hrsg\. von|\(Hrsg\.\)|S\.\s?\d/.test(pre) && SERIES_WORDS.test(pre) && !/^(?:o\. O\.|[A-ZÄÖÜ][\wäöüß-]+)$/.test(pre)) {
      const ser = pre.replace(/,?\s*(?:Bd\.?|Band|Nr\.?|Heft)\s*(\d+(?:\/\d+)?)\s*$/, " $1").replace(/\s+/g, " ").trim();
      return `(= ${ser}), ${after}`;
    }
    if (pre && /hrsg\. von/.test(pre) && !/S\.\s?\d/.test(pre)) {
      // "Oberpfälzer Dokumente der Musikgeschichte, hrsg. von Hermann Beck, Regensburg 1976"
      const hm = pre.match(/^(.*?),?\s*hrsg\. von\s+(.+)$/);
      if (hm) return `${hm[1] ? `(= ${hm[1].trim()}), ` : ""}hrsg. von ${hm[2].trim()}, ${after}`;
    }
  }
  return body;
}

// --- Hauptfunktion ----------------------------------------------------------------

export function formatZitat(entry: { autor: string | null; titel: string | null; kurztitel: string; biblio: string | null }): Zitat {
  const autor = tidyAutor(entry.autor);
  const rawTitle = entry.titel ?? entry.kurztitel;
  const raw = (entry.biblio ?? "").trim();
  const inMatch = raw.match(/^in:\s*/i);
  const body = tidyPlaces(tidyPages(inMatch ? raw.slice(inMatch[0].length) : raw));

  // 1. Zeitschrift / Zeitung / Jahrbuch
  const per = periodical(body);
  if (per) {
    return { art: "zeitschrift", autor, titel: tidyTitel(rawTitle, true), unselbstaendig: true, container: tidyContainer(per.container), rest: finish(per.rest) };
  }

  // 2. Sammelband: explizites "in:", Herausgeberangabe, oder Container + Ort Jahr + Seiten
  const hasEditor = /\(Hrsg\.\)|hrsg\. von/.test(body);
  const hasPages = /(^|[,.]\s*)S\.\s?[\dIVX]/.test(body);
  const placeYearOnly = /^(?:o\. O\.|[A-ZÄÖÜ][\wäöüß.\-/]+(?:\s[A-ZÄÖÜa-zäöüß.][\wäöüß.\-/]*){0,2})\s+(?:o\. J\.|[⁰-⁹]*\d{4})/.test(body);
  // Text vor "Ort Jahr", der kein Reihentitel ist, benennt das übergeordnete Werk
  // ("Festschrift zur Orgelweihe, Augsburg 1982"; "Altbayerische Heimat, Beilage zur
  // Mittelbayerischen Zeitung, Regensburg 1968/1"; "Orgelkunst und Orgelforschung.
  // Gedenkschrift Rudolf Reuter, Kassel u. a. 1990")
  let containerBefore = false;
  const py = lastPlaceYear(body.replace(/[,.]?\s*S\.\s?[\dIVX].*$/, ""));
  if (py && py.index > 0) {
    const pre = body.slice(0, py.index).trim().replace(/[,.]$/, "");
    const words = pre.split(/\s+/).length;
    const periodicalWords = /Beilage|Zeitung|Zeitschrift|Blatt\b|Blätter|Anzeiger|Mitteilungen|Bote\b|Tagblatt|Festschrift|Gedenkschrift|Festgabe|Katalog|Programm/.test(pre);
    if (!/hrsg\. von|\(Hrsg\.\)/.test(pre) && (periodicalWords || (words >= 4 && !SERIES_WORDS.test(pre)))) containerBefore = true;
  }
  // "Bayreuther Tagblatt, Mai 1959" (Zeitung, nur Monat und Jahr)
  const monthOnly = new RegExp(`^(?<name>[^\\d,]+),\\s*(?<datum>(?:${MONTHS})\\.?\\s+\\d{4})$`).exec(body);
  if (monthOnly?.groups && /Tagblatt|Zeitung|Blatt|Blätter|Anzeiger|Bote|Kurier|Post|Ostmark|Nachrichten/.test(monthOnly.groups.name)) {
    return { art: "zeitschrift", autor, titel: tidyTitel(rawTitle, true), unselbstaendig: true, container: tidyContainer(monthOnly.groups.name), rest: `(${monthOnly.groups.datum})` };
  }
  const looksDependent = inMatch !== null || (hasEditor && hasPages) || containerBefore || (hasPages && !placeYearOnly && /\s\d{4}|o\. J\./.test(body));
  if (looksDependent) {
    const col = collection(body);
    if (col) return { art: col.bareNumber ? "zeitschrift" : "sammelband", autor, titel: tidyTitel(rawTitle, true), unselbstaendig: true, container: col.container, rest: finish(col.rest) };
    return { art: "unselbstaendig", autor, titel: tidyTitel(rawTitle, true), unselbstaendig: true, container: null, rest: finish(body) };
  }

  // 3. Monografie
  return { art: "monografie", autor, titel: tidyTitel(rawTitle, false), unselbstaendig: false, container: null, rest: finish(monograph(body)) };
}

function finish(rest: string): string {
  let r = rest.replace(/\s+/g, " ").replace(/[,;\s]+$/, "").trim();
  if (/\.$/.test(r) && !/\b(?:ff?|Aufl|J|O|a|Jh|Diss|mschr|masch|S|Ms|Typoskr|u|e\. V|usw)\.$/.test(r)) r = r.slice(0, -1);
  return r;
}
