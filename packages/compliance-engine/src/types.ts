import type { Severity } from "@regbite/database";

export interface CheckResult {
  ruleId: string;
  ruleName: string;
  status: "PASS" | "FAIL" | "WARNING" | "SKIPPED";
  severity: Severity;
  message: string;
  remediation?: string;
  regulatoryCitation?: string;
}

export interface IngredientComplianceResult {
  ingredientName: string;
  found: boolean;
  fdaStatus: string;
  grasStatus: string;
  ndiRequired: boolean;
  ndiReasoning?: string;
  warningLetterCount: number;
  warningLetterSummaries?: string[];
  safeUsageLevel?: string;
  upperIntakeLevel?: string;
  prop65Listed: boolean;
  advisoryNotes?: string;
  regulatoryCitations: string[];
}

export interface FormulaComplianceResult {
  overallScore: number;
  ingredientResults: IngredientComplianceResult[];
  interactions: InteractionFlag[];
  dosageFlags: DosageFlag[];
  checks: CheckResult[];
}

export interface InteractionFlag {
  ingredients: [string, string];
  severity: Severity;
  description: string;
  citation?: string;
}

export interface DosageFlag {
  ingredientName: string;
  amount: number;
  unit: string;
  upperLimit?: number;
  severity: Severity;
  message: string;
}

export interface LabelValidationResult {
  overallScore: number;
  checks: CheckResult[];
}

export interface ClaimValidationResult {
  claim: string;
  classification: "STRUCTURE_FUNCTION" | "DISEASE" | "HEALTH" | "NUTRIENT_CONTENT";
  isCompliant: boolean;
  riskLevel: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  requiredDisclaimer?: string;
  ftcSubstantiationRequired: boolean;
  enforcementPrecedents: string[];
  suggestedRewrite?: string;
}
