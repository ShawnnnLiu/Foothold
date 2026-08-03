// The landing-page demo button's presets and orchestration. Sixteen real
// routes mined from the committed articulation.db (source of truth:
// data/curated/demo_students/demo_presets.json, generated 2026-08-03): each
// was verified through the real evaluator to yield a healthy AT RISK column
// plus clean, no-articulation, and still-owed findings, and every course code
// resolves exactly through the FTS5 autocomplete. Nothing here fabricates
// data client-side: institutions and majors come from the API rows the
// landing screen already fetched, and chips are confirmed via `resolveCodes`
// exactly like the sample-transcript path.

import type { CourseHit, InstitutionRow, MajorRow } from "./api";
import { resolveCodes } from "./resolve";
import type { RouteContext } from "./route";

export interface DemoPreset {
  sending_id: number;
  sending_name: string;
  receiving_id: number;
  receiving_name: string;
  major_key: string;
  major_label: string;
  courses: string[];
}

export const DEMO_PRESETS: DemoPreset[] = [
  {
    sending_id: 113,
    sending_name: "De Anza College",
    receiving_id: 79,
    receiving_name: "University of California, Berkeley",
    major_key: "76/113/to/79/Major/7d01fb7b-2afa-460e-ace0-08ddbf3f4ee7",
    major_label: "Electrical Engineering & Computer Sciences, B.S.",
    courses: [
      "CIS 22C",
      "MATH 1A",
      "MATH 1B",
      "MATH 1C",
      "MATH 1D",
      "MATH 2A",
      "MATH 2B",
      "ENGR 37",
      "PHYS 4A",
      "PHYS 4B",
      "PHYS 4C",
      "PHYS 4D",
      "CHEM 1A",
      "ACCT 1A",
    ],
  },
  {
    sending_id: 51,
    sending_name: "Foothill College",
    receiving_id: 39,
    receiving_name: "San Jose State University",
    major_key: "76/51/to/39/Major/20817531-45fd-429a-33ef-08ddb349963e",
    major_label: "Forensic Science, Concentration in Biology, B.S.",
    courses: [
      "BIOL 1B",
      "BIOL 1C",
      "CHEM 1A",
      "CHEM 1B",
      "CHEM 1C",
      "PHYS 2A",
      "PHYS 2B",
      "PHYS 2C",
      "BIOL 1A",
      "MATH 1A",
      "ENGL C1000",
      "STAT C1000",
      "CHEM 12A",
      "ACTG 1A",
    ],
  },
  {
    sending_id: 49,
    sending_name: "Pasadena City College",
    receiving_id: 39,
    receiving_name: "San Jose State University",
    major_key: "76/49/to/39/Major/3ccc93fd-a5dc-4e22-3433-08ddb349963e",
    major_label: "Computer Science, B.S.",
    courses: [
      "CS 008",
      "CS 008L",
      "CS 066",
      "CS 066L",
      "CS 003B",
      "CS 003BL",
      "BIOL 010A",
      "BIOL 010B",
      "ENGL C1001",
      "PHYS 008A",
      "PHYS 008B",
      "CHEM 001A",
      "ACCT 001A",
    ],
  },
  {
    sending_id: 103,
    sending_name: "El Camino College",
    receiving_id: 89,
    receiving_name: "University of California, Davis",
    major_key: "76/103/to/89/Major/50941955-9576-4f9f-3462-08ddb349963e",
    major_label: "Marine & Coastal Science B.S. (Marine Ecology & Organismal Biology)",
    courses: [
      "CHEM 7A",
      "CHEM 7B",
      "BIOL 120",
      "MATH 190",
      "MATH 191",
      "PHYS 1B",
      "PHYS 1D",
      "BIOL 110",
      "PHYS 1C",
      "PHYS 1A",
      "PHYS 2A",
      "AJ 100",
    ],
  },
  {
    sending_id: 10,
    sending_name: "Columbia College",
    receiving_id: 42,
    receiving_name: "California State University, Northridge",
    major_key: "76/10/to/42/Major/bffba4e5-6c72-46bf-425c-08dda831fbe0",
    major_label: "COMPUTER SCIENCE, B.S.",
    courses: [
      "GEOGR 15",
      "ESC 62",
      "BIOL 2",
      "BIOL 4",
      "BIOL 6",
      "MATH 18B",
      "MATH 26",
      "MATH 18A",
      "COMP 12J",
      "COMP 11P",
      "CHEM 2A",
      "ANTHR 1",
    ],
  },
  {
    sending_id: 124,
    sending_name: "Irvine Valley College",
    receiving_id: 81,
    receiving_name: "California State University, Long Beach",
    major_key: "76/124/to/81/Major/ce6b8893-8156-4ba2-33ba-08ddb349963e",
    major_label: "Kinesiology, Sport Psychology and Leadership",
    courses: [
      "KNES 11",
      "KNES 20",
      "KNES 25",
      "KNES 4",
      "KNES 61",
      "KNES 76",
      "DNCE 47",
      "IA 35",
      "KNES 71",
      "DNCE 36",
      "DNCE 86",
      "ACCT 1A",
    ],
  },
  {
    sending_id: 74,
    sending_name: "Orange Coast College",
    receiving_id: 89,
    receiving_name: "University of California, Davis",
    major_key: "76/74/to/89/Major/1ad08c27-d4e6-4fef-3474-08ddb349963e",
    major_label: "Computer Science & Engineering B.S.",
    courses: [
      "ENGL A160",
      "ENGL A161",
      "PHYS A185",
      "PHYS A280",
      "PHYS A285",
      "MATH A180",
      "MATH A185",
      "MATH A280",
      "MATH A235",
      "COMM C1000",
      "ENGR A285",
      "MATH A285",
      "ACCT A101",
    ],
  },
  {
    sending_id: 96,
    sending_name: "Chabot College",
    receiving_id: 46,
    receiving_name: "University of California, Riverside",
    major_key: "76/96/to/46/Major/cc6e72cd-5545-456a-4ec2-08de050a3a5e",
    major_label: "Computer Science with Business Applications B.S.",
    courses: [
      "CSCI 14",
      "ECN 1",
      "ECN 2",
      "CSCI 15",
      "MTH 1",
      "MTH 2",
      "MTH 6",
      "MTH 3",
      "BUS 1A",
      "CSCI 20",
      "CSCI 21",
      "ADMJ 50",
    ],
  },
  {
    sending_id: 83,
    sending_name: "College of the Redwoods",
    receiving_id: 11,
    receiving_name: "California Polytechnic University, San Luis Obispo",
    major_key: "76/83/to/11/Major/e0eb8add-48f9-4510-c15b-08ddf49aba41",
    major_label: "COMPUTER SCIENCE, B.S.",
    courses: [
      "PHIL 13",
      "PHIL 20",
      "MATH 50B",
      "MATH 50A",
      "PHYS 4A",
      "PHYS 4B",
      "PHYS 4C",
      "MATH 3",
      "CIS 18",
      "MATH 45",
      "BIOL 1",
      "BIOL 3",
      "CHEM 1A",
      "AG 17",
    ],
  },
  {
    sending_id: 142,
    sending_name: "Cosumnes River College",
    receiving_id: 42,
    receiving_name: "California State University, Northridge",
    major_key: "76/142/to/42/Major/ab31771b-7302-4ebb-4284-08dda831fbe0",
    major_label: "BIOLOGY, B.A.",
    courses: [
      "MATH 372",
      "MATH 373",
      "BIOL 400",
      "BIOL 410",
      "BIOL 420",
      "MATH 355",
      "CHEM 401",
      "CHEM 400",
      "PHYS 360",
      "PHYS 350",
      "ACCT 301",
    ],
  },
  {
    sending_id: 86,
    sending_name: "Los Angeles Pierce College",
    receiving_id: 117,
    receiving_name: "University of California, Los Angeles",
    major_key: "76/86/to/117/Major/1b02a731-f51b-472a-1f81-08ddcb96df9e",
    major_label: "Human Biology and Society/B.S.",
    courses: [
      "PHILOS 020",
      "CHICANO 002",
      "CHICANO 008",
      "MATH 263",
      "MATH 261",
      "MATH 262",
      "ANTHRO 101",
      "BIOLOGY 006",
      "PHYSICS 101",
      "ACCTG 001",
    ],
  },
  {
    sending_id: 137,
    sending_name: "Santa Monica College",
    receiving_id: 89,
    receiving_name: "University of California, Davis",
    major_key: "76/137/to/89/Major/866a2a39-a2c2-467d-34b0-08ddb349963e",
    major_label: "Psychology B.S.",
    courses: [
      "BIOL 3",
      "PHYSCS 6",
      "PHYSCS 7",
      "MATH 8",
      "MATH 7",
      "STAT C1000",
      "PSYCH 7",
      "PSYC C1000",
      "CHEM 21",
      "ACCTG 1",
    ],
  },
  {
    sending_id: 126,
    sending_name: "Sacramento City College",
    receiving_id: 46,
    receiving_name: "University of California, Riverside",
    major_key: "76/126/to/46/Major/8427a541-f341-4c6d-4eda-08de050a3a5e",
    major_label: "Plant Biology, B.A. or B.S.",
    courses: [
      "MATH 355",
      "MATH 356",
      "MATH 401",
      "MATH 400",
      "BIOL 402",
      "BIOL 412",
      "BIOL 422",
      "CHEM 400",
      "CHEM 401",
      "ACCT 301",
    ],
  },
  {
    sending_id: 45,
    sending_name: "San Diego Miramar College",
    receiving_id: 129,
    receiving_name: "California State University, Fullerton",
    major_key: "76/45/to/129/Major/27286dda-89a1-432d-8114-08dd55dbff27",
    major_label: "Computer Science, B.S.",
    courses: [
      "CISC 192",
      "CISC 190",
      "BIOL 210B",
      "GEOL 100",
      "GEOL 101",
      "GEOL 111",
      "MATH 252",
      "CHEM 200",
      "ACCT 116A",
    ],
  },
  {
    sending_id: 56,
    sending_name: "Palomar College",
    receiving_id: 132,
    receiving_name: "University of California, Santa Cruz",
    major_key: "76/56/to/132/Major/76d4ee50-28ac-451b-1ffc-08ddcb96df9e",
    major_label: "Molecular, Cell, and Developmental Biology B.S.",
    courses: [
      "CHEM 110",
      "CHEM 115",
      "CHEM 115L",
      "BIOL 200",
      "CHEM 220",
      "MATH 140",
      "CHEM 221",
      "PHYS 200",
      "AAS 100",
    ],
  },
  {
    sending_id: 108,
    sending_name: "MiraCosta College",
    receiving_id: 89,
    receiving_name: "University of California, Davis",
    major_key: "76/108/to/89/Major/015909c4-e18a-4aa9-3459-08ddb349963e",
    major_label: "Business B.S.",
    courses: [
      "MATH 150",
      "MATH 155",
      "MATH 260",
      "ACCT 201",
      "ACCT 202",
      "ECON 102",
      "ECON 101",
      "BTEC 180",
      "ADM 100",
    ],
  },
];

// The random source is injected so the pick stays a pure, testable function;
// the screen passes Math.random from the click handler (event input, not
// render state - rendering the chosen preset stays deterministic).
export function pickDemoIndex(
  count: number,
  random: () => number,
  exclude: number | null = null,
): number {
  const index = Math.min(Math.floor(random() * count), count - 1);
  if (exclude !== null && count > 1 && index === exclude) {
    return (index + 1) % count;
  }
  return index;
}

export interface DemoDeps {
  ccs: InstitutionRow[];
  targets: InstitutionRow[];
  fetchMajors: (sendingId: number, receivingId: number) => Promise<{ majors: MajorRow[] }>;
  search: (institutionId: number, q: string) => Promise<CourseHit[]>;
}

export interface DemoStart {
  route: RouteContext;
  chips: CourseHit[];
  unresolved: string[];
}

export async function assembleDemo(preset: DemoPreset, deps: DemoDeps): Promise<DemoStart> {
  const sending = deps.ccs.find((row) => row.assist_id === preset.sending_id);
  const receiving = deps.targets.find((row) => row.assist_id === preset.receiving_id);
  if (!sending || !receiving) {
    throw new Error(
      `demo route unavailable: ${preset.sending_name} → ${preset.receiving_name} not in the institution lists`,
    );
  }
  const body = await deps.fetchMajors(preset.sending_id, preset.receiving_id);
  const major = body.majors.find((row) => row.assist_key === preset.major_key);
  if (!major) {
    throw new Error(`demo major unavailable: ${preset.major_label}`);
  }
  const result = await resolveCodes([...preset.courses], (q) => deps.search(preset.sending_id, q));
  if (result.resolved.length === 0) {
    throw new Error("demo courses did not resolve against the autocomplete index");
  }
  return {
    route: { sending, receiving, major },
    chips: result.resolved,
    unresolved: result.unresolved,
  };
}
