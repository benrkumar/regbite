/**
 * cGMP Readiness Checker — 21 CFR Part 111
 *
 * Current Good Manufacturing Practice in Manufacturing, Packaging,
 * Labeling, or Holding Operations for Dietary Supplements.
 *
 * References:
 *   21 CFR Part 111 — cGMP for dietary supplements
 *   FDA Guidance: "Small Entity Compliance Guide" for 21 CFR Part 111 (2010)
 */

import { calculateComplianceScore } from '../scoring/score-calculator.js';
import type { CheckResult } from '../types.js';

export type CGMPSectionId =
  | 'personnel'
  | 'plant'
  | 'equipment'
  | 'production'
  | 'laboratory'
  | 'records'
  | 'complaints';

export interface CGMPCheckItem {
  id: string;
  question: string;
  guidance: string;
  citation: string;
  severity: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';
}

export interface CGMPSection {
  id: CGMPSectionId;
  title: string;
  description: string;
  cfr: string;
  items: CGMPCheckItem[];
}

export interface CGMPAuditInput {
  [sectionId: string]: {
    [itemId: string]: boolean | null; // true=compliant, false=non-compliant, null=N/A
  };
}

export interface CGMPSectionResult {
  sectionId: CGMPSectionId;
  title: string;
  score: number;
  totalItems: number;
  compliantItems: number;
  nonCompliantItems: number;
  naItems: number;
  checks: CheckResult[];
}

export interface CGMPAuditResult {
  overallScore: number;
  sections: CGMPSectionResult[];
  criticalGaps: string[];
  recommendedActions: string[];
}

// ── 21 CFR Part 111 sections and check items ──────────────────────────────────

export const CGMP_SECTIONS: CGMPSection[] = [
  {
    id: 'personnel',
    title: 'Personnel Qualifications',
    description: 'Qualification and training requirements for all personnel involved in manufacturing dietary supplements.',
    cfr: '21 CFR §§ 111.12–111.16',
    items: [
      {
        id: 'PERS-001',
        question: 'Do all personnel performing manufacturing operations have the education, training, or experience to perform their assigned functions?',
        guidance: 'Document training records for each employee covering cGMP, hygiene, safety, and their specific job functions.',
        citation: '21 CFR § 111.12',
        severity: 'HIGH',
      },
      {
        id: 'PERS-002',
        question: 'Are personnel who may have an illness, open lesion, or other abnormal source of contamination excluded from operations that could contaminate the product?',
        guidance: 'Implement a written illness/injury policy and require personnel to report conditions that could compromise product quality.',
        citation: '21 CFR § 111.14(b)(1)',
        severity: 'CRITICAL',
      },
      {
        id: 'PERS-003',
        question: 'Do personnel wear appropriate clothing (hair covers, gloves, protective garments) to protect the dietary supplement from contamination?',
        guidance: 'Define and enforce dress code requirements in your SOPs. Include frequency of changing protective garments.',
        citation: '21 CFR § 111.14(b)(2)',
        severity: 'HIGH',
      },
      {
        id: 'PERS-004',
        question: 'Is there a qualified individual who oversees the manufacturing operations (Quality Person)?',
        guidance: 'A quality control individual must be designated to ensure the overall quality of operations. They must have adequate education or experience.',
        citation: '21 CFR § 111.12(b)',
        severity: 'CRITICAL',
      },
      {
        id: 'PERS-005',
        question: 'Are training records maintained and current for all manufacturing personnel?',
        guidance: 'Training records must be retained and made available for FDA inspection. Include dates, topics, and trainer information.',
        citation: '21 CFR § 111.14(a)',
        severity: 'HIGH',
      },
    ],
  },
  {
    id: 'plant',
    title: 'Physical Plant & Grounds',
    description: 'Requirements for the design and maintenance of facilities used in manufacturing dietary supplements.',
    cfr: '21 CFR §§ 111.15–111.20',
    items: [
      {
        id: 'PLANT-001',
        question: 'Is the physical plant of adequate size and construction to allow operations to be performed under sanitary conditions?',
        guidance: 'Ensure sufficient space for equipment, materials, and personnel movement. Separate raw materials from finished products.',
        citation: '21 CFR § 111.15(a)',
        severity: 'HIGH',
      },
      {
        id: 'PLANT-002',
        question: 'Is there adequate lighting in all areas where components, containers, labels, or dietary supplements are examined or processed?',
        guidance: 'Proper lighting prevents errors and contamination. Consider lux requirements for inspection areas.',
        citation: '21 CFR § 111.15(c)',
        severity: 'MEDIUM',
      },
      {
        id: 'PLANT-003',
        question: 'Is there adequate ventilation to minimize dust, airborne contamination, and temperature/humidity extremes?',
        guidance: 'HVAC systems should be validated for critical manufacturing areas. Document temperature and humidity records for moisture-sensitive products.',
        citation: '21 CFR § 111.15(d)',
        severity: 'HIGH',
      },
      {
        id: 'PLANT-004',
        question: 'Is there an effective pest control program in place?',
        guidance: 'Pest control contracts, inspection logs, and corrective actions must be documented. No pesticides that could contaminate components may be used in manufacturing areas.',
        citation: '21 CFR § 111.15(e)',
        severity: 'CRITICAL',
      },
      {
        id: 'PLANT-005',
        question: 'Are sanitation schedules and procedures documented and implemented for all areas?',
        guidance: 'Written cleaning SOPs must cover frequency, cleaning agents, and responsibility. Sanitation logs must be maintained.',
        citation: '21 CFR § 111.15(b)',
        severity: 'HIGH',
      },
      {
        id: 'PLANT-006',
        question: 'Are plumbing systems and water supplies adequate and free from backflow contamination risk?',
        guidance: 'Water used in manufacturing must meet quality standards. Document water testing results. Prevent cross-connection with non-potable water.',
        citation: '21 CFR § 111.15(g)',
        severity: 'HIGH',
      },
    ],
  },
  {
    id: 'equipment',
    title: 'Equipment & Utensils',
    description: 'Requirements for equipment used in manufacturing, packaging, labeling, or holding dietary supplements.',
    cfr: '21 CFR §§ 111.25–111.35',
    items: [
      {
        id: 'EQUIP-001',
        question: 'Is all equipment constructed so it can be adequately cleaned and maintained?',
        guidance: 'Equipment in contact with dietary supplements must be made of materials that do not react with or contaminate the product (e.g., food-grade stainless steel).',
        citation: '21 CFR § 111.27(a)',
        severity: 'HIGH',
      },
      {
        id: 'EQUIP-002',
        question: 'Are equipment calibration and maintenance logs maintained?',
        guidance: 'Document calibration schedules, calibration dates, results, and technician information. Calibrate all measuring instruments before use.',
        citation: '21 CFR § 111.27(b)',
        severity: 'HIGH',
      },
      {
        id: 'EQUIP-003',
        question: 'Are equipment cleaning procedures documented and followed?',
        guidance: 'Written cleaning SOPs must define cleaning agents, procedures, frequency, and responsible personnel. Clean between product runs to prevent cross-contamination.',
        citation: '21 CFR § 111.27(c)',
        severity: 'CRITICAL',
      },
      {
        id: 'EQUIP-004',
        question: 'Are instruments used to measure product identity, purity, strength, or composition calibrated at appropriate intervals?',
        guidance: 'Instruments include scales, pH meters, HPLC, spectrophotometers. Calibration with NIST-traceable standards is recommended.',
        citation: '21 CFR § 111.27(b)',
        severity: 'HIGH',
      },
    ],
  },
  {
    id: 'production',
    title: 'Production & Process Controls',
    description: 'Requirements for manufacturing processes, batch production records, and quality controls.',
    cfr: '21 CFR §§ 111.55–111.140',
    items: [
      {
        id: 'PROD-001',
        question: 'Does each dietary supplement have a written master manufacturing record (MMR)?',
        guidance: 'MMR must include: name, batch size, complete list of components with quantities, step-by-step instructions, in-process controls, equipment to be used, and label specifications.',
        citation: '21 CFR § 111.205',
        severity: 'CRITICAL',
      },
      {
        id: 'PROD-002',
        question: 'Is a batch production record (BPR) created for each batch manufactured?',
        guidance: 'BPR must document: batch ID, dates, component lot numbers, weights, in-process test results, deviations, and who performed each step.',
        citation: '21 CFR § 111.255',
        severity: 'CRITICAL',
      },
      {
        id: 'PROD-003',
        question: 'Are all dietary supplement components (raw materials) tested for identity before use?',
        guidance: 'At minimum, you must conduct one test to verify the identity of each component. FDA recommends testing for strength, purity, and composition as well.',
        citation: '21 CFR § 111.75(a)(1)',
        severity: 'CRITICAL',
      },
      {
        id: 'PROD-004',
        question: 'Are finished dietary supplement batches tested before release to verify they meet specifications?',
        guidance: 'Must test for: identity, purity, strength, and composition. Also test for contamination that may adulterate the supplement.',
        citation: '21 CFR § 111.75(c)',
        severity: 'CRITICAL',
      },
      {
        id: 'PROD-005',
        question: 'Are product specifications established and documented for each dietary supplement?',
        guidance: 'Specifications must cover: identity, purity, strength, composition, and limits for contamination (heavy metals, microbials, etc.).',
        citation: '21 CFR § 111.70',
        severity: 'HIGH',
      },
      {
        id: 'PROD-006',
        question: 'Is there a written procedure for handling out-of-specification (OOS) results?',
        guidance: 'OOS investigation procedure must: quarantine the batch, investigate root cause, and determine disposition (reject, reprocess, or release with justification).',
        citation: '21 CFR § 111.113',
        severity: 'HIGH',
      },
      {
        id: 'PROD-007',
        question: 'Are returned dietary supplements evaluated and documented before being disposed of or reintroduced to inventory?',
        guidance: 'Returned products must be evaluated to determine if they are suitable for redistribution or must be destroyed. Records must be maintained.',
        citation: '21 CFR § 111.535',
        severity: 'MEDIUM',
      },
    ],
  },
  {
    id: 'laboratory',
    title: 'Laboratory Operations',
    description: 'Requirements for laboratory controls, testing, and reserve samples.',
    cfr: '21 CFR §§ 111.303–111.325',
    items: [
      {
        id: 'LAB-001',
        question: 'Are written procedures for all laboratory tests established and followed?',
        guidance: 'Testing SOPs must include: test method, equipment used, reagents, acceptance/rejection criteria, and sample handling procedures.',
        citation: '21 CFR § 111.303',
        severity: 'HIGH',
      },
      {
        id: 'LAB-002',
        question: 'Are reserve (retention) samples retained for each dietary supplement batch?',
        guidance: 'Retain samples from each batch for at least 1 year beyond the product\'s shelf life or 2 years from manufacture date, whichever is longer. Samples must be stored under conditions consistent with labeling.',
        citation: '21 CFR § 111.83',
        severity: 'HIGH',
      },
      {
        id: 'LAB-003',
        question: 'Are laboratory records maintained for all tests performed?',
        guidance: 'Lab records must include: sample ID, test method, test date, analyst, raw data, calculations, results, and pass/fail determination.',
        citation: '21 CFR § 111.320(b)',
        severity: 'HIGH',
      },
      {
        id: 'LAB-004',
        question: 'Are reference standards of appropriate quality used for testing?',
        guidance: 'Use USP or other compendial standards when available. For identity testing of botanical ingredients, use authenticated voucher specimens or validated methods.',
        citation: '21 CFR § 111.310',
        severity: 'MEDIUM',
      },
    ],
  },
  {
    id: 'records',
    title: 'Records & Recordkeeping',
    description: 'Requirements for maintaining manufacturing records, making them available for FDA inspection.',
    cfr: '21 CFR §§ 111.375–111.415',
    items: [
      {
        id: 'REC-001',
        question: 'Are all required manufacturing records retained for at least 1 year beyond the shelf life or 2 years from manufacture date?',
        guidance: 'Applies to: master manufacturing records, batch production records, laboratory records, distribution records, and complaint records.',
        citation: '21 CFR § 111.375',
        severity: 'CRITICAL',
      },
      {
        id: 'REC-002',
        question: 'Are records kept at the place of manufacture or accessible for FDA inspection within 24 hours of request?',
        guidance: 'Records may be stored offsite or electronically if they can be retrieved and printed within 24 hours upon request by an FDA investigator.',
        citation: '21 CFR § 111.375(c)',
        severity: 'HIGH',
      },
      {
        id: 'REC-003',
        question: 'Are distribution records maintained identifying the batch, lot number, and destination for each shipment?',
        guidance: 'Distribution records must enable rapid and complete traceability/recall of any batch within 24 hours.',
        citation: '21 CFR § 111.410',
        severity: 'CRITICAL',
      },
      {
        id: 'REC-004',
        question: 'Are all entries in records made in real-time (contemporaneous documentation)?',
        guidance: 'Do not backfill records. All entries must be made at the time the activity is performed, signed by the responsible person.',
        citation: '21 CFR § 111.375(b)',
        severity: 'HIGH',
      },
    ],
  },
  {
    id: 'complaints',
    title: 'Complaints & Adverse Events',
    description: 'Requirements for handling consumer complaints and serious adverse event reporting.',
    cfr: '21 CFR §§ 111.553–111.570',
    items: [
      {
        id: 'COMP-001',
        question: 'Is there a written procedure for receiving and evaluating consumer complaints?',
        guidance: 'Procedure must designate a qualified person to review all complaints and conduct investigations where appropriate.',
        citation: '21 CFR § 111.553',
        severity: 'HIGH',
      },
      {
        id: 'COMP-002',
        question: 'Are consumer complaint records maintained for each complaint received?',
        guidance: 'Records must include: complaint description, date received, batch/lot number identified, investigative findings, and any corrective actions taken.',
        citation: '21 CFR § 111.570',
        severity: 'HIGH',
      },
      {
        id: 'COMP-003',
        question: 'Are Serious Adverse Events (SAEs) reported to FDA within 15 business days?',
        guidance: 'SAEs include: death, life-threatening illness, hospitalization, persistent disability, birth defects, or events requiring medical intervention. Submit via FDA MedWatch.',
        citation: '21 U.S.C. § 342(f)(1)(C); 21 CFR § 111.570',
        severity: 'CRITICAL',
      },
      {
        id: 'COMP-004',
        question: 'Are records of all serious adverse events retained for at least 6 years?',
        guidance: 'SAE records must be maintained for 6 years from the date of occurrence. This exceeds the standard manufacturing record retention requirement.',
        citation: '21 U.S.C. § 379aa-1',
        severity: 'HIGH',
      },
    ],
  },
];

// ── Scoring and result generation ──────────────────────────────────────────────

export function scoreCGMPAudit(input: CGMPAuditInput): CGMPAuditResult {
  const sectionResults: CGMPSectionResult[] = [];
  const criticalGaps: string[] = [];
  const allChecks: CheckResult[] = [];

  for (const section of CGMP_SECTIONS) {
    const sectionInput = input[section.id] ?? {};
    const checks: CheckResult[] = [];
    let compliant = 0;
    let nonCompliant = 0;
    let na = 0;

    for (const item of section.items) {
      const response = sectionInput[item.id];
      if (response === null || response === undefined) {
        na++;
        checks.push({
          ruleId: item.id,
          ruleName: item.question.slice(0, 80),
          status: 'SKIPPED',
          severity: item.severity,
          message: 'Not assessed',
          regulatoryCitation: item.citation,
        });
      } else if (response === true) {
        compliant++;
        checks.push({
          ruleId: item.id,
          ruleName: item.question.slice(0, 80),
          status: 'PASS',
          severity: item.severity,
          message: item.guidance.slice(0, 120),
          regulatoryCitation: item.citation,
        });
      } else {
        nonCompliant++;
        checks.push({
          ruleId: item.id,
          ruleName: item.question.slice(0, 80),
          status: 'FAIL',
          severity: item.severity,
          message: `Non-compliant: ${item.guidance.slice(0, 120)}`,
          remediation: item.guidance,
          regulatoryCitation: item.citation,
        });
        if (item.severity === 'CRITICAL') {
          criticalGaps.push(`[${section.title}] ${item.question.slice(0, 100)}`);
        }
      }
    }

    const assessed = compliant + nonCompliant;
    const score = assessed === 0 ? 100 : Math.round((compliant / assessed) * 100);

    sectionResults.push({
      sectionId: section.id,
      title: section.title,
      score,
      totalItems: section.items.length,
      compliantItems: compliant,
      nonCompliantItems: nonCompliant,
      naItems: na,
      checks,
    });

    allChecks.push(...checks);
  }

  const overallScore = calculateComplianceScore(allChecks);

  const recommendedActions = buildRecommendations(sectionResults, criticalGaps);

  return {
    overallScore,
    sections: sectionResults,
    criticalGaps,
    recommendedActions,
  };
}

function buildRecommendations(sections: CGMPSectionResult[], criticalGaps: string[]): string[] {
  const actions: string[] = [];

  if (criticalGaps.length > 0) {
    actions.push(`Immediately address ${criticalGaps.length} CRITICAL gap(s) before any FDA inspection.`);
  }

  const lowestScoreSection = [...sections]
    .filter((s) => s.nonCompliantItems > 0)
    .sort((a, b) => a.score - b.score)[0];

  if (lowestScoreSection) {
    actions.push(`Prioritize ${lowestScoreSection.title} — currently at ${lowestScoreSection.score}% compliance with ${lowestScoreSection.nonCompliantItems} gap(s).`);
  }

  const recordsSection = sections.find((s) => s.sectionId === 'records');
  if (recordsSection && recordsSection.score < 100) {
    actions.push('Ensure all required records are complete and accessible within 24 hours for FDA inspection.');
  }

  actions.push('Conduct internal cGMP audits at least annually. Schedule a third-party audit every 2–3 years.');
  actions.push('Train all new personnel on 21 CFR Part 111 requirements before they begin manufacturing activities.');

  return actions;
}

export function getCGMPSections(): CGMPSection[] {
  return CGMP_SECTIONS;
}

export function buildEmptyAuditInput(): CGMPAuditInput {
  const result: CGMPAuditInput = {};
  for (const section of CGMP_SECTIONS) {
    result[section.id] = {};
    for (const item of section.items) {
      result[section.id][item.id] = null;
    }
  }
  return result;
}
