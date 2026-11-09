// Korrigiert offensichtliche Leerzeichen-/Satzzeichenfehler, die aus der
// Access-Quelle stammen (z.B. "ehem.Seminar", "Hauptstr.44", "S.20ff,129ff",
// "( 2007/2008)", "S.18 f.."). Bewusst konservativ: nur Muster, bei denen die
// Korrektur eindeutig ist. Historische Schreibweisen, Zeichen wie " : " aus
// Katalogtiteln (ISBD) oder Registernamen wie "OctavCoppel" bleiben unberührt.
//
// Wird zur Build-Zeit auf alle geladenen Daten angewendet (lib/data.ts) und
// im Browser auf die Orgelliste und die Kartenpopups - die Rohdaten (ETL-
// Ausgabe) bleiben unverändert, ein erneuter ETL-Lauf bleibt also gültig.

const WORD = "A-Za-zÄÖÜäöüß";

const EXPLICIT: [string, string][] = [
  ["freistehenderSpieltisch", "freistehender Spieltisch"],
  ["freieKombinationen", "freie Kombinationen"],
  ["pneumatischeSpiel", "pneumatische Spiel"],
  ["inLandshut", "in Landshut"],
  ["ArsOrgani", "Ars Organi"],
];

const RULES: [RegExp, string | ((...m: string[]) => string)][] = [
  // "ehem.Seminar", "evang.Kirche", "St.Mang", "Ped.Komb.I" -> Leerzeichen nach Abkürzungspunkt
  [new RegExp(`([${WORD}]{2,})\\.(?=[A-ZÄÖÜ][a-zäöüß]|[IVX]{1,4}\\b)`, "g"), "$1. "],
  // "S.20", "Nr.10", "Bd.7", "Op.16", "Hauptstr.44" -> Leerzeichen vor der Zahl
  [/(\b(?:S|H|Nr|Bd|Op|Jg|Hft|Heft)|[Ss]tr)\.(?=\d)/g, "$1. "],
  // "1.Man." -> "1. Man."
  [/\b(\d{1,2})\.(?=[A-ZÄÖÜ][a-zäöüß])/g, "$1. "],
  // Seitenlisten "S. 20ff,129ff,235" -> "S. 20ff, 129ff, 235"
  [
    /\b(S\. ?)(\d+\s?(?:ff?\.?)?(?:,\s?\d+\s?(?:ff?\.?)?)+)/g,
    (_m: string, a: string, b: string) => a + b.replace(/,(?=\d)/g, ", "),
  ],
  // "Hessenthal,Hauptstr." -> Leerzeichen nach Komma zwischen Wörtern
  [new RegExp(`([${WORD}]{3,}),(?=[${WORD}])`, "g"), "$1, "],
  // "Züge:II/I" -> "Züge: II/I"
  [/([a-zäöüß]{3,}):(?=[A-ZÄÖÜ])/g, "$1: "],
  // "( 2007/2008)" / "Subbaß )" -> Klammern ohne Innenabstand
  [/\([ \t]+/g, "("],
  [/[ \t]+\)/g, ")"],
  // "Fischer , Untermain", "(1985) ." -> kein Leerzeichen vor Komma/Punkt
  [/(?<=[\p{L}\p{N})]) +,(?= )/gu, ","],
  [/(?<=[\p{L}\p{N})]) +\.(?=\s|$)/gu, "."],
  // "Generalcrescendo, , Walze" -> ein Komma
  [/,[ ]+,/g, ","],
  // "S.18 f.." / "o.J.." -> ein Punkt (Auslassungspunkte "..." bleiben)
  [/(?<=[\p{L}\p{N}])\.\.(?!\.)/gu, "."],
  // "z.B.", "u.a.", "d.h.", "o.J." -> mit Leerzeichen (z. B., u. a., d. h., o. J.)
  [/\b([zudo])\.([BahJ])\.(?!\p{L})/gu, "$1. $2."],
  // "Hofstetter(2008)" -> "Hofstetter (2008)"
  [/([a-zäöüß]{3,})\((?=\d{4}\))/g, "$1 ("],
];

export function fixText(s: string): string {
  if (!s || s.startsWith("http://") || s.startsWith("https://")) return s;
  let out = s;
  for (const [from, to] of EXPLICIT) {
    if (out.includes(from)) out = out.split(from).join(to);
  }
  for (const [re, rep] of RULES) {
    out = out.replace(re, rep as string);
  }
  return out;
}

// Wendet fixText rekursiv auf alle Strings eines geladenen JSON-Objekts an
// (in-place, Schlüssel bleiben unverändert).
export function fixDeep<T>(value: T): T {
  if (typeof value === "string") return fixText(value) as unknown as T;
  if (Array.isArray(value)) {
    for (let i = 0; i < value.length; i++) value[i] = fixDeep(value[i]);
    return value;
  }
  if (value && typeof value === "object") {
    const obj = value as Record<string, unknown>;
    for (const k of Object.keys(obj)) obj[k] = fixDeep(obj[k]);
  }
  return value;
}
