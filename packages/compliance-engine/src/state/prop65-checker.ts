/**
 * Prop 65 Checker — California Safe Drinking Water and Toxic Enforcement Act of 1986
 *
 * References:
 *   Cal. Health & Safety Code § 25249.5 et seq.
 *   OEHHA Title 27, CCR § 25600 — Safe harbor warning regulations
 *   California Prop 65 Chemical List (OEHHA)
 */

import { prisma, Prisma } from '@regbite/database';
import type { CheckResult } from '../types.js';

export interface Prop65CheckInput {
  ingredients: { name: string; casNumber?: string }[];
  targetMarkets: string[];
  hasCaliforniaWarning?: boolean;
}

export interface Prop65ChemicalMatch {
  ingredientName: string;
  chemicalName: string;
  casNumber: string | null;
  listingMechanism: string | null;
  type: 'CARCINOGEN' | 'REPRODUCTIVE_TOXICANT' | 'BOTH' | 'UNKNOWN';
}

export interface Prop65CheckResult {
  targetsCalifornia: boolean;
  chemicalsFound: Prop65ChemicalMatch[];
  warningRequired: boolean;
  checks: CheckResult[];
  warningLanguage?: string;
}

const SHORT_FORM_WARNING = 'WARNING: This product can expose you to chemicals including [CHEMICAL], which is known to the State of California to cause [EFFECT]. For more information go to www.P65Warnings.ca.gov.';

function detectType(mechanism: string | null): Prop65ChemicalMatch['type'] {
  if (!mechanism) return 'UNKNOWN';
  const m = mechanism.toLowerCase();
  const isCancer = m.includes('cancer') || m.includes('carcino') || m.includes('labor');
  const isRepro = m.includes('reproduc') || m.includes('develop') || m.includes('birth');
  if (isCancer && isRepro) return 'BOTH';
  if (isCancer) return 'CARCINOGEN';
  if (isRepro) return 'REPRODUCTIVE_TOXICANT';
  return 'UNKNOWN';
}

export async function checkProp65(input: Prop65CheckInput): Promise<Prop65CheckResult> {
  const targetsCalifornia = input.targetMarkets.some((m) =>
    m.toLowerCase().includes('california') || m.toLowerCase().includes('ca') || m.toLowerCase() === 'all',
  );

  const checks: CheckResult[] = [];
  const chemicalsFound: Prop65ChemicalMatch[] = [];

  if (!targetsCalifornia) {
    checks.push({
      ruleId: 'PROP65-001',
      ruleName: 'California market targeting',
      status: 'PASS',
      severity: 'LOW',
      message: 'Product is not targeted at the California market — Prop 65 requirements do not apply.',
      regulatoryCitation: 'Cal. Health & Safety Code § 25249.5',
    });
    return { targetsCalifornia: false, chemicalsFound: [], warningRequired: false, checks };
  }

  // Cross-reference ingredients against Prop 65 chemical list
  for (const ingredient of input.ingredients) {
    const nameQuery = ingredient.name.toLowerCase().trim();

    const match = await prisma.prop65Chemical.findFirst({
      where: {
        OR: [
          ingredient.casNumber ? { casNumber: ingredient.casNumber } : { casNumber: 'NEVER' },
          { chemical: { contains: nameQuery, mode: Prisma.QueryMode.insensitive } },
        ].filter((c) => Object.keys(c).length > 0),
      },
    });

    if (match) {
      const type = detectType(match.listingMechanism);
      chemicalsFound.push({
        ingredientName: ingredient.name,
        chemicalName: match.chemical,
        casNumber: match.casNumber,
        listingMechanism: match.listingMechanism,
        type,
      });
    }
  }

  if (chemicalsFound.length === 0) {
    checks.push({
      ruleId: 'PROP65-001',
      ruleName: 'Prop 65 chemical screening',
      status: 'PASS',
      severity: 'LOW',
      message: 'No Prop 65 listed chemicals detected in the ingredient list.',
      remediation: 'Verify against the full OEHHA Prop 65 list as it is updated regularly (twice per year).',
      regulatoryCitation: 'OEHHA Title 27, CCR §§ 25600–25602',
    });
    return { targetsCalifornia, chemicalsFound: [], warningRequired: false, checks };
  }

  // Chemicals found — warning required unless safe harbor exemption applies
  const warningRequired = !input.hasCaliforniaWarning;

  for (const chem of chemicalsFound) {
    const effect = chem.type === 'CARCINOGEN' ? 'cancer'
      : chem.type === 'REPRODUCTIVE_TOXICANT' ? 'birth defects or other reproductive harm'
      : 'cancer and reproductive harm';

    checks.push({
      ruleId: `PROP65-${chem.casNumber ?? chem.chemicalName.slice(0, 8).toUpperCase()}`,
      ruleName: `Prop 65: ${chem.chemicalName}`,
      status: input.hasCaliforniaWarning ? 'PASS' : 'FAIL',
      severity: 'CRITICAL',
      message: `${chem.chemicalName} (from ${chem.ingredientName}) is on the California Prop 65 list as a known ${effect}.`,
      remediation: input.hasCaliforniaWarning
        ? 'Prop 65 warning is present.'
        : `Add a California Prop 65 warning to the product label: "${SHORT_FORM_WARNING.replace('[CHEMICAL]', chem.chemicalName).replace('[EFFECT]', effect)}"`,
      regulatoryCitation: 'Cal. Health & Safety Code § 25249.6; OEHHA Title 27, CCR § 25603',
    });
  }

  const firstChem = chemicalsFound[0];
  const effect = firstChem.type === 'CARCINOGEN' ? 'cancer'
    : firstChem.type === 'REPRODUCTIVE_TOXICANT' ? 'birth defects or other reproductive harm'
    : 'cancer and reproductive harm';

  const warningLanguage = SHORT_FORM_WARNING
    .replace('[CHEMICAL]', firstChem.chemicalName)
    .replace('[EFFECT]', effect);

  return {
    targetsCalifornia,
    chemicalsFound,
    warningRequired,
    checks,
    warningLanguage: warningRequired ? warningLanguage : undefined,
  };
}
