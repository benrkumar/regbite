/**
 * Label validator — 21 CFR § 101.36
 *
 * 10 mandatory check functions covering the FDA Supplement Facts panel
 * requirements for dietary supplements.
 */

import { prisma } from '@regbite/database';
import { calculateComplianceScore } from '../scoring/score-calculator.js';
import { cite } from '../utils/citation-builder.js';
import type { CheckResult, LabelValidationResult } from '../types.js';

export interface SupplementFactsInput {
  servingSize?: string;
  servingsPerContainer?: string | number;
  nutrients?: NutrientEntry[];
  proprietaryBlend?: ProprietaryBlendInput;
  otherIngredients?: string[];
  allergens?: string[];
  netQuantity?: string;
  identityStatement?: string;
  manufacturerInfo?: string;
  lotCode?: string | null;
  hasExpirationDate?: boolean;
  hasDisclaimers?: string[];
}

interface NutrientEntry {
  name: string;
  amount: number;
  unit: string;
  dvPercent?: number | null;
}

interface ProprietaryBlendInput {
  name: string;
  totalAmount: number;
  unit: string;
  ingredients: string[];
}

const BIG_9_ALLERGENS = [
  'milk', 'eggs', 'fish', 'shellfish', 'tree nuts', 'peanuts', 'wheat', 'soybeans', 'sesame',
];

// Nutrients that MUST appear on Supplement Facts if present above threshold
const MANDATORY_NUTRIENTS_IF_PRESENT = [
  'Vitamin A', 'Vitamin C', 'Vitamin D', 'Vitamin E', 'Vitamin K',
  'Thiamin', 'Riboflavin', 'Niacin', 'Vitamin B6', 'Folate', 'Vitamin B12',
  'Biotin', 'Pantothenic Acid', 'Calcium', 'Iron', 'Phosphorus',
  'Iodine', 'Magnesium', 'Zinc', 'Selenium', 'Copper', 'Manganese', 'Chromium', 'Molybdenum',
  'Chloride', 'Potassium', 'Choline',
];

// ── Check functions ────────────────────────────────────────────────────────────

function checkServingSize(input: SupplementFactsInput): CheckResult {
  const id = 'LABEL-001';
  const name = 'Serving size declaration';
  const citation = cite('21_CFR_101.36');

  if (!input.servingSize) {
    return {
      ruleId: id, ruleName: name, status: 'FAIL', severity: 'HIGH',
      message: 'Serving size is missing from the Supplement Facts panel.',
      remediation: 'Declare a serving size in common household measures (e.g., "1 capsule", "2 tablets", "1 scoop (10 g)").',
      regulatoryCitation: citation,
    };
  }

  // Serving size should be in a recognized unit or common household measure
  const validPattern = /\d+(\.\d+)?\s*(capsule|tablet|softgel|scoop|ml|g|oz|tbsp|tsp|packet|serving)/i;
  if (!validPattern.test(input.servingSize)) {
    return {
      ruleId: id, ruleName: name, status: 'WARNING', severity: 'MEDIUM',
      message: `Serving size "${input.servingSize}" may not be in a recognized household measure format.`,
      remediation: 'Use a common household measure or unit (e.g., "2 capsules", "1 scoop (15 g)").',
      regulatoryCitation: citation,
    };
  }

  return {
    ruleId: id, ruleName: name, status: 'PASS', severity: 'LOW',
    message: `Serving size declared: "${input.servingSize}"`,
    regulatoryCitation: citation,
  };
}

function checkServingsPerContainer(input: SupplementFactsInput): CheckResult {
  const id = 'LABEL-002';
  const name = 'Servings per container';
  const citation = cite('21_CFR_101.36');

  if (!input.servingsPerContainer) {
    return {
      ruleId: id, ruleName: name, status: 'FAIL', severity: 'MEDIUM',
      message: 'Servings per container is missing.',
      remediation: 'Declare the number of servings per container immediately below the serving size.',
      regulatoryCitation: citation,
    };
  }

  return {
    ruleId: id, ruleName: name, status: 'PASS', severity: 'LOW',
    message: `Servings per container: ${input.servingsPerContainer}`,
    regulatoryCitation: citation,
  };
}

async function checkDailyValueAccuracy(input: SupplementFactsInput): Promise<CheckResult> {
  const id = 'LABEL-003';
  const name = 'Daily Value (% DV) accuracy';
  const citation = cite('21_CFR_101.36');

  if (!input.nutrients?.length) {
    return {
      ruleId: id, ruleName: name, status: 'SKIPPED', severity: 'LOW',
      message: 'No nutrients declared — DV check skipped.',
      regulatoryCitation: citation,
    };
  }

  const dvTable = await prisma.fDADailyValue.findMany();
  const dvMap = new Map(dvTable.map((dv) => [dv.nutrient.toLowerCase(), dv.dvAdult]));

  const errors: string[] = [];
  for (const nutrient of input.nutrients) {
    if (nutrient.dvPercent == null) continue;
    const dvAdult = dvMap.get(nutrient.name.toLowerCase());
    if (!dvAdult) continue;

    const expectedDv = Math.round((nutrient.amount / dvAdult) * 100);
    const declared = nutrient.dvPercent;
    const tolerance = Math.max(2, expectedDv * 0.1); // ±10% or ±2 percentage points

    if (Math.abs(declared - expectedDv) > tolerance) {
      errors.push(`${nutrient.name}: declared ${declared}% DV, calculated ${expectedDv}% DV`);
    }
  }

  if (errors.length) {
    return {
      ruleId: id, ruleName: name, status: 'FAIL', severity: 'HIGH',
      message: `Daily Value percentage errors found: ${errors.join('; ')}`,
      remediation: 'Recalculate % DV using FDA reference values from 21 CFR § 101.36 Table 2 (adults and children ≥4 years).',
      regulatoryCitation: citation,
    };
  }

  return {
    ruleId: id, ruleName: name, status: 'PASS', severity: 'LOW',
    message: 'All declared % DV values are within acceptable tolerance.',
    regulatoryCitation: citation,
  };
}

function checkProprietaryBlend(input: SupplementFactsInput): CheckResult {
  const id = 'LABEL-004';
  const name = 'Proprietary blend disclosure';
  const citation = cite('21_CFR_101.36');

  if (!input.proprietaryBlend) {
    return {
      ruleId: id, ruleName: name, status: 'PASS', severity: 'LOW',
      message: 'No proprietary blend declared.',
      regulatoryCitation: citation,
    };
  }

  const blend = input.proprietaryBlend;
  const issues: string[] = [];

  if (!blend.name) issues.push('Blend must have a name (e.g., "Proprietary Blend" or a branded name)');
  if (!blend.totalAmount || blend.totalAmount <= 0) issues.push('Total weight of the proprietary blend must be declared');
  if (!blend.ingredients?.length) issues.push('Individual ingredients within the blend must be listed');

  if (issues.length) {
    return {
      ruleId: id, ruleName: name, status: 'FAIL', severity: 'HIGH',
      message: `Proprietary blend disclosure deficiencies: ${issues.join('; ')}`,
      remediation: `Under 21 CFR § 101.36(b)(3), a proprietary blend must: (1) be identified by a name, (2) declare the total weight, (3) list individual ingredients in descending order of predominance.`,
      regulatoryCitation: citation,
    };
  }

  return {
    ruleId: id, ruleName: name, status: 'PASS', severity: 'LOW',
    message: `Proprietary blend "${blend.name}" declared at ${blend.totalAmount} ${blend.unit} with ${blend.ingredients.length} listed ingredients.`,
    regulatoryCitation: citation,
  };
}

function checkOtherIngredients(input: SupplementFactsInput): CheckResult {
  const id = 'LABEL-005';
  const name = '"Other Ingredients" declaration';
  const citation = cite('21_CFR_101.36');

  if (!input.otherIngredients?.length) {
    return {
      ruleId: id, ruleName: name, status: 'PASS', severity: 'LOW',
      message: 'No other ingredients declared (or none present).',
      regulatoryCitation: citation,
    };
  }

  // Other ingredients must be listed outside the Supplement Facts box
  // in descending order of predominance by weight
  return {
    ruleId: id, ruleName: name, status: 'PASS', severity: 'LOW',
    message: `Other ingredients listed: ${input.otherIngredients.slice(0, 5).join(', ')}${input.otherIngredients.length > 5 ? '...' : ''}`,
    remediation: 'Ensure "Other Ingredients" are listed outside the Supplement Facts box in descending order of predominance.',
    regulatoryCitation: citation,
  };
}

function checkAllergens(input: SupplementFactsInput): CheckResult {
  const id = 'LABEL-006';
  const name = 'Major food allergen declaration';
  const citation = 'FALCPA (21 U.S.C. § 343(w)); FASTER Act (2023)';

  const otherIngredientsText = (input.otherIngredients ?? []).join(' ').toLowerCase();
  const nutrientsText = (input.nutrients ?? []).map((n) => n.name).join(' ').toLowerCase();
  const allText = `${otherIngredientsText} ${nutrientsText}`;

  const detectedAllergens: string[] = [];
  for (const allergen of BIG_9_ALLERGENS) {
    if (allText.includes(allergen)) {
      detectedAllergens.push(allergen);
    }
  }

  const declaredAllergens = (input.allergens ?? []).map((a) => a.toLowerCase());
  const undeclared = detectedAllergens.filter((a) => !declaredAllergens.includes(a));

  if (undeclared.length) {
    return {
      ruleId: id, ruleName: name, status: 'FAIL', severity: 'CRITICAL',
      message: `Potential major food allergen(s) detected in ingredients but not declared: ${undeclared.join(', ')}.`,
      remediation: 'Add "Contains: [allergen(s)]" statement to the label or include allergen declaration in the ingredient list.',
      regulatoryCitation: citation,
    };
  }

  return {
    ruleId: id, ruleName: name, status: 'PASS', severity: 'LOW',
    message: detectedAllergens.length ? `Allergens declared: ${detectedAllergens.join(', ')}` : 'No major food allergens detected.',
    regulatoryCitation: citation,
  };
}

function checkNetQuantity(input: SupplementFactsInput): CheckResult {
  const id = 'LABEL-007';
  const name = 'Net quantity of contents statement';
  const citation = '21 CFR § 101.105';

  if (!input.netQuantity) {
    return {
      ruleId: id, ruleName: name, status: 'FAIL', severity: 'MEDIUM',
      message: 'Net quantity of contents is missing from the principal display panel.',
      remediation: 'Declare the net quantity in both metric and US customary units on the bottom 30% of the principal display panel.',
      regulatoryCitation: citation,
    };
  }

  return {
    ruleId: id, ruleName: name, status: 'PASS', severity: 'LOW',
    message: `Net quantity declared: "${input.netQuantity}"`,
    regulatoryCitation: citation,
  };
}

function checkIdentityStatement(input: SupplementFactsInput): CheckResult {
  const id = 'LABEL-008';
  const name = 'Statement of identity';
  const citation = '21 CFR § 101.3; DSHEA (21 U.S.C. § 321(ff))';

  if (!input.identityStatement) {
    return {
      ruleId: id, ruleName: name, status: 'FAIL', severity: 'MEDIUM',
      message: 'Statement of identity is missing. Dietary supplements must include "Dietary Supplement" as part of the identity statement.',
      remediation: 'Add a statement of identity that includes the term "Dietary Supplement" or an appropriate descriptor (e.g., "Vitamin C Dietary Supplement").',
      regulatoryCitation: citation,
    };
  }

  const hasDietarySupplementTerm = /dietary supplement/i.test(input.identityStatement);
  if (!hasDietarySupplementTerm) {
    return {
      ruleId: id, ruleName: name, status: 'WARNING', severity: 'MEDIUM',
      message: `Identity statement "${input.identityStatement}" does not include "Dietary Supplement".`,
      remediation: 'The identity statement should include "Dietary Supplement" per 21 CFR § 101.3 and DSHEA.',
      regulatoryCitation: citation,
    };
  }

  return {
    ruleId: id, ruleName: name, status: 'PASS', severity: 'LOW',
    message: `Identity statement: "${input.identityStatement}"`,
    regulatoryCitation: citation,
  };
}

function checkManufacturerInfo(input: SupplementFactsInput): CheckResult {
  const id = 'LABEL-009';
  const name = 'Manufacturer / distributor name and address';
  const citation = '21 CFR § 101.5';

  if (!input.manufacturerInfo) {
    return {
      ruleId: id, ruleName: name, status: 'FAIL', severity: 'HIGH',
      message: 'Manufacturer or distributor name and address is missing. This is required on all dietary supplement labels.',
      remediation: 'Include the name, street address (or city/state/ZIP for well-known firms), and country of the manufacturer or distributor.',
      regulatoryCitation: citation,
    };
  }

  return {
    ruleId: id, ruleName: name, status: 'PASS', severity: 'LOW',
    message: `Manufacturer info present: "${input.manufacturerInfo.slice(0, 80)}..."`,
    regulatoryCitation: citation,
  };
}

function checkLotAndExpiration(input: SupplementFactsInput): CheckResult {
  const id = 'LABEL-010';
  const name = 'Lot code and expiration date';
  const citation = '21 CFR Part 111 (cGMP)';

  const issues: string[] = [];
  if (!input.lotCode) issues.push('lot code not present');
  if (!input.hasExpirationDate) issues.push('expiration or best-by date not present');

  if (issues.length === 2) {
    return {
      ruleId: id, ruleName: name, status: 'WARNING', severity: 'MEDIUM',
      message: 'Neither lot code nor expiration date found. Both are required under cGMP regulations (21 CFR Part 111).',
      remediation: 'Include a lot code and expiration or best-by date on each unit container.',
      regulatoryCitation: citation,
    };
  } else if (issues.length === 1) {
    return {
      ruleId: id, ruleName: name, status: 'WARNING', severity: 'LOW',
      message: `Partial cGMP marking — ${issues[0]} detected as missing.`,
      remediation: 'Include both lot code and expiration date per 21 CFR Part 111 cGMP requirements.',
      regulatoryCitation: citation,
    };
  }

  return {
    ruleId: id, ruleName: name, status: 'PASS', severity: 'LOW',
    message: 'Lot code and expiration date present.',
    regulatoryCitation: citation,
  };
}

// ── Main validator ─────────────────────────────────────────────────────────────

export async function validateLabel(input: SupplementFactsInput): Promise<LabelValidationResult> {
  const checks: CheckResult[] = [
    checkServingSize(input),
    checkServingsPerContainer(input),
    await checkDailyValueAccuracy(input),
    checkProprietaryBlend(input),
    checkOtherIngredients(input),
    checkAllergens(input),
    checkNetQuantity(input),
    checkIdentityStatement(input),
    checkManufacturerInfo(input),
    checkLotAndExpiration(input),
  ];

  return {
    overallScore: calculateComplianceScore(checks),
    checks,
  };
}
