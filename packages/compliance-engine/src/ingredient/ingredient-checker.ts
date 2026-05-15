/**
 * Ingredient compliance checker — core module
 *
 * Given an ingredient name or CAS number, queries the RegBite ingredient
 * database and returns a full FDA compliance profile including:
 * - FDA status (PERMITTED / RESTRICTED / BANNED / ADVISORY / UNKNOWN)
 * - GRAS status
 * - NDI requirement evaluation
 * - Warning letter count and summaries
 * - Prop 65 listing
 * - Safe usage and upper intake levels
 */

import { prisma } from '@regbite/database';
import { normalizeIngredientName } from '../utils/normalize.js';
import { evaluateNDIRequirement } from './ndi-evaluator.js';
import { buildCitations } from '../utils/citation-builder.js';
import type { IngredientComplianceResult, CheckResult } from '../types.js';

export interface IngredientInput {
  name: string;
  casNumber?: string | null;
  amount?: number;
  unit?: string;
}

export async function checkIngredient(input: IngredientInput): Promise<IngredientComplianceResult & { checks: CheckResult[] }> {
  const checks: CheckResult[] = [];
  const normalizedName = normalizeIngredientName(input.name);

  // ── DB lookup ──────────────────────────────────────────────────────────────
  const record = await prisma.uSIngredient.findFirst({
    where: input.casNumber
      ? { casNumber: input.casNumber }
      : {
          OR: [
            { name: { contains: normalizedName, mode: 'insensitive' } },
            { aliases: { has: input.name } },
          ],
        },
    include: {
      warningLetterLinks: {
        include: { warningLetter: { select: { letterId: true, subject: true, companyName: true } } },
      },
    },
  });

  if (!record) {
    checks.push({
      ruleId: 'ING-001',
      ruleName: 'Ingredient in RegBite database',
      status: 'WARNING',
      severity: 'MEDIUM',
      message: `"${input.name}" was not found in the RegBite ingredient database. Manual review required.`,
      remediation: 'Verify the ingredient name and spelling. If this is a novel ingredient, an NDI notification may be required.',
      regulatoryCitation: 'DSHEA § 8 (21 U.S.C. § 350b)',
    });

    return {
      ingredientName: input.name,
      found: false,
      fdaStatus: 'UNKNOWN',
      grasStatus: 'UNKNOWN',
      ndiRequired: true,
      ndiReasoning: 'Ingredient not found in database — assumed to be a New Dietary Ingredient requiring FDA notification.',
      warningLetterCount: 0,
      prop65Listed: false,
      regulatoryCitations: buildCitations(['DSHEA_NDI']),
      checks,
    };
  }

  const wlSummaries = record.warningLetterLinks
    .slice(0, 5)
    .map((l) => `${l.warningLetter.companyName}: ${l.warningLetter.subject ?? 'No subject'}`);

  const ndi = evaluateNDIRequirement({
    dsheaGrandfathered: record.dsheaGrandfathered,
    ndiNotificationsCount: record.ndiNotificationsCount,
    grasStatus: record.grasStatus,
    fdaStatus: record.fdaStatus,
    ingredientName: record.name,
  });

  // ── Check: FDA status ──────────────────────────────────────────────────────
  if (record.fdaStatus === 'BANNED') {
    checks.push({
      ruleId: 'ING-010',
      ruleName: 'FDA banned ingredient',
      status: 'FAIL',
      severity: 'CRITICAL',
      message: `${record.name} is BANNED by the FDA and cannot be included in dietary supplements sold in the United States.`,
      remediation: 'Remove this ingredient from the formulation immediately.',
      regulatoryCitation: record.advisoryNotes ?? 'FDA Dietary Supplement Enforcement',
    });
  } else if (record.fdaStatus === 'RESTRICTED') {
    checks.push({
      ruleId: 'ING-011',
      ruleName: 'FDA restricted ingredient',
      status: 'FAIL',
      severity: 'HIGH',
      message: `${record.name} has RESTRICTED status. ${record.advisoryNotes ?? 'Specific conditions or dose limits apply.'}`,
      remediation: 'Verify the specific restriction details and ensure all conditions are met before including this ingredient.',
      regulatoryCitation: 'FDA Dietary Supplement Ingredient Advisory List',
    });
  } else if (record.fdaStatus === 'ADVISORY') {
    checks.push({
      ruleId: 'ING-012',
      ruleName: 'FDA advisory ingredient',
      status: 'WARNING',
      severity: 'HIGH',
      message: `${record.name} is on the FDA advisory list. ${record.advisoryNotes ?? ''}`,
      remediation: 'Consult current FDA advisory guidance before use. Consider consumer-facing safety disclosures.',
      regulatoryCitation: 'FDA Dietary Supplement Ingredient Advisory List',
    });
  } else if (record.fdaStatus === 'PERMITTED') {
    checks.push({
      ruleId: 'ING-010',
      ruleName: 'FDA permitted ingredient',
      status: 'PASS',
      severity: 'LOW',
      message: `${record.name} is permitted for use in dietary supplements.`,
      regulatoryCitation: 'DSHEA (21 U.S.C. § 321(ff))',
    });
  } else {
    checks.push({
      ruleId: 'ING-010',
      ruleName: 'FDA status',
      status: 'WARNING',
      severity: 'MEDIUM',
      message: `FDA status for ${record.name} is UNKNOWN. Verification required.`,
      remediation: 'Confirm this ingredient qualifies as a lawful dietary supplement ingredient under DSHEA.',
    });
  }

  // ── Check: NDI notification ────────────────────────────────────────────────
  if (ndi.ndiRequired) {
    checks.push({
      ruleId: 'ING-020',
      ruleName: 'NDI notification required',
      status: 'FAIL',
      severity: 'CRITICAL',
      message: `${record.name} requires a 75-day pre-market NDI notification to the FDA before marketing. ${ndi.reasoning}`,
      remediation: 'Submit an NDI notification to FDA at least 75 days before marketing this ingredient.',
      regulatoryCitation: 'DSHEA § 8 (21 U.S.C. § 350b)',
    });
  } else {
    checks.push({
      ruleId: 'ING-020',
      ruleName: 'NDI notification',
      status: 'PASS',
      severity: 'LOW',
      message: ndi.reasoning,
      regulatoryCitation: ndi.exemption,
    });
  }

  // ── Check: Warning letters ─────────────────────────────────────────────────
  if (record.warningLetterLinks.length > 2) {
    checks.push({
      ruleId: 'ING-030',
      ruleName: 'Warning letter history',
      status: 'WARNING',
      severity: 'MEDIUM',
      message: `${record.name} has been cited in ${record.warningLetterLinks.length} FDA warning letters. This indicates elevated regulatory scrutiny.`,
      remediation: 'Review warning letter content to understand specific violations and ensure your formulation avoids similar issues.',
    });
  }

  // ── Check: Prop 65 ─────────────────────────────────────────────────────────
  if (record.prop65Listed) {
    checks.push({
      ruleId: 'ING-040',
      ruleName: 'California Prop 65',
      status: 'WARNING',
      severity: 'HIGH',
      message: `${record.name} is listed under California Proposition 65. Products sold in California may require a Prop 65 warning label.`,
      remediation: 'Assess whether the exposure level exceeds Prop 65 safe harbor levels. If selling in California, include required Prop 65 warning.',
      regulatoryCitation: 'California Proposition 65 (Health & Safety Code § 25249.5)',
    });
  }

  // ── Check: Upper intake level (if amount provided) ─────────────────────────
  if (input.amount && record.upperIntakeLevel) {
    checks.push({
      ruleId: 'ING-050',
      ruleName: 'Upper intake level reference',
      status: 'WARNING',
      severity: 'MEDIUM',
      message: `NIH established Upper Tolerable Intake Level for ${record.name}: ${record.upperIntakeLevel}. Verify your serving dose is within safe limits.`,
      remediation: 'Cross-reference your serving dose against NIH Tolerable Upper Intake Levels.',
      regulatoryCitation: 'NIH Office of Dietary Supplements',
    });
  }

  const regulatoryCitations = Array.isArray(record.regulatoryCitations)
    ? (record.regulatoryCitations as string[])
    : [];

  return {
    ingredientName: record.name,
    found: true,
    fdaStatus: record.fdaStatus,
    grasStatus: record.grasStatus,
    ndiRequired: ndi.ndiRequired,
    ndiReasoning: ndi.reasoning,
    warningLetterCount: record.warningLetterLinks.length,
    warningLetterSummaries: wlSummaries,
    safeUsageLevel: record.safeUsageLevel ?? undefined,
    upperIntakeLevel: record.upperIntakeLevel ?? undefined,
    prop65Listed: record.prop65Listed,
    advisoryNotes: record.advisoryNotes ?? undefined,
    regulatoryCitations,
    checks,
  };
}
