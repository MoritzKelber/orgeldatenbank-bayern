// Löst nicht gängige Abkürzungen in den Kurztiteln der Literatur auf
// ("Neue O" -> "Neue Orgeln", "Schwäbische Ob" -> "Schwäbische Orgelbauer",
// "FS München" -> "Festschrift München" ...). Gängige Abkürzungen (St., Hl.,
// o. J., ca., Nr.) und Autoreninitialen bleiben stehen.
//
// Gilt nur für Kurztitel (literature.json) und die Zitierstrings der Orgeln
// (organ.literatur[].lit), die aus denselben Kurztiteln plus Seitenzahl
// bestehen - nicht für Dispositionen o. Ä., wo "Ob" oder "O" etwas anderes
// bedeuten können.

const L = "A-Za-zÄÖÜäöüß";
const lb = `(?<![${L}])`;
const rb = `(?![${L}])`;
const w = (word: string) => new RegExp(`${lb}${word}${rb}`, "g");

const RULES: [RegExp, string][] = [
  // "O" = Orgel/Orgeln/Organa (kontextabhängig)
  [new RegExp(`${lb}O (Bambergensia|Benedictina|Cisterciensia|Franciscana)`, "g"), "Organa $1"],
  [/Unbekanntes O-Land/g, "Unbekanntes Orgelland"],
  [/Bavarian O\b/g, "Bavarian Organs"],
  [/\bAlte O\b/g, "Alte Orgel"],
  [/\bGeschichte der O\b/g, "Geschichte der Orgel"],
  [/\bDie O\b/g, "Die Orgel"],
  [/\bO der Reger-Zeit/g, "Orgel der Reger-Zeit"],
  [/\bO der Gegenwart/g, "Orgeln der Gegenwart"],
  [new RegExp(`${lb}(Neue|Süddeutsche|Eichstätter|Ingolstädter|Nürnberger|Hölzerne|Regensburgs) O${rb}`, "g"), "$1 Orgeln"],
  // "Ob" = Orgelbauer
  [/\bMeyer-Siat\/Reichling, OB-Liste/g, "Meyer-Siat/Reichling, Orgelbauer-Liste"],
  [/\/OB\b/g, "/Oberbayern"],
  [w("Ob"), "Orgelbauer"],

  // Publikationstypen am Anfang des Kurztitels
  [/^FS(?= )/, "Festschrift"],
  [/^KF(?= )/, "Kirchenführer"],
  [/^FI(?= )/, "Firmenschrift"],
  [/^PR(?= )/, "Programm"],
  [/^KT(?= )/, "Kunsttopographie"],
  [/^KMM(?= )/, "Kirchenmusikalische Mitteilungen"],
  [/^HB(?= )/, "Handbuch"],
  [/^Bayr\.(?= )/, "Bayerische"],
  [/\bBayr\. Ob/g, "Bayerische Ob"],

  // Autorenkürzel / Institutionen
  [new RegExp(`/W\\.(?=[,\\s]|$)`, "g"), "/Wohnhaas"],
  [/\bBDO\b/g, "Bund Deutscher Orgelbaumeister"],
  [/\b100 J\. /g, "100 Jahre "],
  [w("ULF"), "Unsere Liebe Frau"],
  [w("Dek\\."), "Dekanat"],

  // Wörter
  [w("Lkr\\."), "Landkreis"],
  [w("Bayr\\."), "Bayerische"],
  [w("Bayer\\."), "Bayerische"],
  [w("Kunstdenkm\\."), "Kunstdenkmäler"],
  [w("Werkverz\\."), "Werkverzeichnis"],
  [w("Rez\\."), "Rezension"],
  [w("Mü\\."), "München"],
  [w("Krankenh\\."), "Krankenhaus"],
  [/Barmh\. Br\./g, "Barmherzige Brüder"],
  [/Marianhiller Kr\./g, "Mariannhiller Krankenhaus"],
  [/am Kr\./g, "am Kreuz"],
  [/St\.Johann B\./g, "St. Johann Baptist"],
  [w("Bapt\\."), "Baptist"],
  [/\bChr\. (Auferstehung|Himmelfahrt)/g, "Christi $1"],
  [w("Opf\\."), "Oberpfalz"],
  [/\/A\./g, "/Aisch"],
  [/\/M\./g, "/Main"],
  [/\/D\./g, "/Donau"],
  [/\/T\./g, "/Tauber"],
  [/\/Rh\./g, "/Rhön"],
  [/\/Allg\./g, "/Allgäu"],
  [/St\.Peter u\. A\./g, "St. Peter und Alexander"],
  [w("Joh\\.k\\."), "Johanneskirche"],
  [w("Haidh\\."), "Haidhausen"],
  [w("Gögg\\."), "Göggingen"],
  [w("Bär\\."), "Bärenkeller"],
  [w("Untermenz\\."), "Untermenzing"],
  [w("Gast\\."), "Gasteig"],
  [w("All\\."), "Allach"],
  [w("Hasenb\\."), "Hasenbergl"],
  [w("Stiftsk\\."), "Stiftskirche"],
  [w("Jesuitenk\\."), "Jesuitenkirche"],
  [w("Katharinenk\\."), "Katharinenkirche"],
  [w("Neupfarrk\\."), "Neupfarrkirche"],
  [w("Frauenk\\."), "Frauenkirche"],
  [/Alte Kap\./g, "Alte Kapelle"],
  [/Univ\.-kirche/g, "Universitätskirche"],
  [w("Östl\\."), "Östliches"],
  [w("Westl\\."), "Westliches"],
  [w("süddt\\."), "süddeutschen"],
  [w("ma\\."), "mittelalterliche"],
  [w("zw\\."), "zwischen"],
  [w("Niederrhein\\."), "Niederrheinische"],
  [w("Mittelfränk\\."), "Mittelfränkischer"],
  [w("Altbayer\\."), "Altbayerische"],
  [w("Dominik\\."), "Dominikanerinnen"],
  [w("Engl\\."), "Englische"],
  [w("Evang\\."), "Evangelische"],
  [w("Lit\\."), "Literatur"],
  [w("ev\\."), "evangelisch"],
];

export function expandKurztitel(s: string): string {
  if (!s) return s;
  let out = s;
  for (const [re, rep] of RULES) out = out.replace(re, rep);
  return out;
}
