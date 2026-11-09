// Build-time data access over the JSON written by etl/src/pipeline.py.
// Only used from .astro frontmatter / getStaticPaths (Node, at build
// time) - never imported from client-side islands, since the full organ
// shards (~65MB total) must not end up in a browser bundle. Client-side
// filtering reads /data/organs-index.json (in public/) directly via
// fetch() instead - see components/FilterPanel.
import fs from "node:fs";
import path from "node:path";
import { fixDeep } from "./textfix";
import type { Builder, LiteraturEntry, Organ, Person, PersonRecord } from "./types";

const DATA_DIR = path.resolve(process.cwd(), "src/data");

function readJSON<T>(relPath: string): T {
  const full = path.join(DATA_DIR, relPath);
  // fixDeep: korrigiert fehlende Leerzeichen etc. in den Quelltexten, s. textfix.ts
  return fixDeep(JSON.parse(fs.readFileSync(full, "utf-8"))) as T;
}

let organsCache: Organ[] | null = null;
let organsByIdCache: Map<number, Organ> | null = null;

export function getAllOrgans(): Organ[] {
  if (organsCache) return organsCache;
  const organsDir = path.join(DATA_DIR, "organs");
  const files = fs.readdirSync(organsDir).filter((f) => f.endsWith(".json"));
  organsCache = files.flatMap((f) => readJSON<Organ[]>(path.join("organs", f)));
  return organsCache;
}

function getOrgansById(): Map<number, Organ> {
  if (organsByIdCache) return organsByIdCache;
  organsByIdCache = new Map(getAllOrgans().map((o) => [o.id, o]));
  return organsByIdCache;
}

export function getOrganById(id: number): Organ | undefined {
  return getOrgansById().get(id);
}

let buildersCache: Builder[] | null = null;
export function getAllBuilders(): Builder[] {
  if (!buildersCache) buildersCache = readJSON<Builder[]>("builders.json");
  return buildersCache;
}

export function getBuilderById(id: number): Builder | undefined {
  return getAllBuilders().find((b) => b.id === id);
}

// The Lemma layer (getAllBuilders, above) stays exactly as the ETL writes
// it - this just extracts a second, independent layer from it, one entry
// per individual person rather than per surname-lemma, each with its own
// id/URL. Derived at build time from the same builders.json rather than
// a separately-maintained file, so there is only one place the person
// data can drift from the lemma data: nowhere.
let personenCache: PersonRecord[] | null = null;
export function getAllPersonen(): PersonRecord[] {
  if (!personenCache) {
    personenCache = getAllBuilders().flatMap((lemma) =>
      (lemma.personen ?? []).map((person: Person) => ({
        id: `${lemma.id}-${person.index}`,
        lemma_id: lemma.id,
        lemma_name: lemma.name,
        ...person,
      })),
    );
  }
  return personenCache;
}

export function getPersonById(id: string): PersonRecord | undefined {
  return getAllPersonen().find((p) => p.id === id);
}

let literatureCache: LiteraturEntry[] | null = null;
export function getAllLiterature(): LiteraturEntry[] {
  if (!literatureCache) literatureCache = readJSON<LiteraturEntry[]>("literature.json");
  return literatureCache;
}

export function getLiteraturBySlug(slug: string): LiteraturEntry | undefined {
  return getAllLiterature().find((l) => l.slug === slug);
}

let lkrCache: string[] | null = null;
export function getAllLandkreise(): string[] {
  if (!lkrCache) lkrCache = readJSON<string[]>("lkr.json");
  return lkrCache;
}
