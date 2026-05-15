/**
 * Formula compliance checker
 *
 * Runs ingredient-level checks on every ingredient in a formulation,
 * checks for known interactions, validates dosages against NIH upper
 * intake levels, and returns an aggregate compliance score.
 */

import { checkIngredient, type IngredientInput } from '../ingredient/ingredient-checker.js';
import { checkInteractions } from './interaction-checker.js';
import { calculateComplianceScore } from '../scoring/score-calculator.js';
import type { FormulaComplianceResult, CheckResult, DosageFlag } from '../types.js';

export interface FormulationIngredient {
  name: string;
  casNumber?: string | null;
  amount?: number;
  unit?: string;
}

export interface FormulaCheckInput {
  ingredients: FormulationIngredient[];
  servingSize?: string;
}

// NIH Tolerable Upper Intake Levels (simplified map for dose validation)
// Values in mg/day unless noted. Source: NIH ODS / Dietary Reference Intakes
const UPPER_INTAKE_LEVELS_MG: Record<string, number> = {
  'vitamin a': 3,       // 3000 mcg RAE = 10000 IU — stored as 3 (mcg x1000)
  'vitamin d': 0.1,     // 100 mcg = 4000 IU
  'vitamin e': 1000,    // 1000 mg alpha-tocopherol
  'vitamin b6': 100,    // 100 mg
  'niacin': 35,         // 35 mg (nicotinic acid form)
  'folate': 1,          // 1000 mcg = 1 mg
  'vitamin c': 2000,    // 2000 mg
  'calcium': 2500,      // 2500 mg
  'iron': 45,           // 45 mg
  'zinc': 40,           // 40 mg
  'selenium': 0.4,      // 400 mcg
  'copper': 10,         // 10 mg
  'magnesium': 350,     // 350 mg (supplemental only)
  'iodine': 1.1,        // 1100 mcg
  'manganese': 11,      // 11 mg
  'phosphorus': 4000,   // 4000 mg
  'chromium picolinate': 1000, // 1000 mcg — conservative
};

function checkDosage(ing: FormulationIngredient): DosageFlag | null {
  if (!ing.amount || !ing.unit) return null;
  const normalizedName = ing.name.toLowerCase().replace(/[()[\]]/g, '').trim();

  for (const [key, ulMg] of Object.entries(UPPER_INTAKE_LEVELS_MG)) {
    if (!normalizedName.includes(key)) continue;

    const unit = ing.unit.toLowerCase();
    let amountMg = ing.amount;
    if (unit === 'g') amountMg = ing.amount * 1000;
    else if (unit === 'mcg' || unit === 'µg') amountMg = ing.amount / 1000;
    else if (unit === 'iu') amountMg = ing.amount * 0.025; // rough IU→mg for fat-soluble vitamins

    if (amountMg > ulMg) {
      const severityCalc = amountMg > ulMg * 2 ? 'HIGH' : 'MEDIUM';
      return {
        ingredientName: ing.name,
        amount: ing.amount,
        unit: ing.unit,
        upperLimit: ulMg,
        severity: severityCalc as DosageFlag['severity'],
        message: `${ing.name} dose (${ing.amount} ${ing.unit}/serving) exceeds NIH Tolerable Upper Intake Level of ~${ulMg} mg/day. May pose safety risk at this level.`,
      };
    }
  }

  return null;
}

export async function checkFormula(input: FormulaCheckInput): Promise<FormulaComplianceResult> {
  const ingredientResults = await Promise.all(
    input.ingredients.map((ing) =>
      checkIngredient(ing as IngredientInput),
    ),
  );

  const allChecks: CheckResult[] = ingredientResults.flatMap((r) => r.checks);

  const interactions = checkInteractions(input.ingredients.map((i) => i.name));

  // Convert interaction flags to CheckResult entries
  for (const interaction of interactions) {
    allChecks.push({
      ruleId: 'FORM-INTERACT',
      ruleName: 'Ingredient interaction',
      status: interaction.severity === 'LOW' ? 'WARNING' : 'FAIL',
      severity: interaction.severity,
      message: `Interaction: ${interaction.ingredients.join(' + ')} — ${interaction.description}`,
      regulatoryCitation: interaction.citation,
    });
  }

  // Dosage checks
  const dosageFlags: DosageFlag[] = [];
  for (const ing of input.ingredients) {
    const flag = checkDosage(ing);
    if (flag) {
      dosageFlags.push(flag);
      allChecks.push({
        ruleId: 'FORM-DOSE',
        ruleName: 'Dose vs. NIH upper intake level',
        status: 'WARNING',
        severity: flag.severity,
        message: flag.message,
        regulatoryCitation: 'NIH Office of Dietary Supplements — Tolerable Upper Intake Levels',
      });
    }
  }

  // Formula-level checks
  const bannedCount = ingredientResults.filter((r) => r.fdaStatus === 'BANNED').length;
  if (bannedCount > 0) {
    allChecks.push({
      ruleId: 'FORM-001',
      ruleName: 'No banned ingredients',
      status: 'FAIL',
      severity: 'CRITICAL',
      message: `Formulation contains ${bannedCount} FDA-banned ingredient(s). Products containing banned ingredients cannot be marketed as dietary supplements.`,
      remediation: 'Remove all banned ingredients before proceeding.',
      regulatoryCitation: 'DSHEA (21 U.S.C. § 321(ff)); FDA Enforcement',
    });
  }

  const ndiRequiredCount = ingredientResults.filter((r) => r.ndiRequired).length;
  if (ndiRequiredCount > 0) {
    allChecks.push({
      ruleId: 'FORM-002',
      ruleName: 'NDI notifications pending',
      status: 'FAIL',
      severity: 'CRITICAL',
      message: `${ndiRequiredCount} ingredient(s) require NDI notifications before this formulation can be marketed.`,
      remediation: 'Submit NDI notifications for all New Dietary Ingredients at least 75 days before marketing.',
      regulatoryCitation: 'DSHEA § 8 (21 U.S.C. § 350b)',
    });
  }

  const overallScore = calculateComplianceScore(allChecks);

  return {
    overallScore,
    ingredientResults: ingredientResults.map(({ checks: _, ...r }) => r),
    interactions,
    dosageFlags,
    checks: allChecks,
  };
}
