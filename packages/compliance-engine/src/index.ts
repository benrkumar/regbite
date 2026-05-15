export type {
  CheckResult,
  IngredientComplianceResult,
  FormulaComplianceResult,
  LabelValidationResult,
  ClaimValidationResult,
  InteractionFlag,
  DosageFlag,
} from './types.js';

export { calculateComplianceScore, calculateCriticalScore } from './scoring/score-calculator.js';

export { checkIngredient } from './ingredient/ingredient-checker.js';
export { evaluateNDIRequirement } from './ingredient/ndi-evaluator.js';
export type { IngredientInput } from './ingredient/ingredient-checker.js';
export type { NDIEvaluationResult } from './ingredient/ndi-evaluator.js';

export { checkFormula } from './formula/formula-checker.js';
export { checkInteractions } from './formula/interaction-checker.js';
export type { FormulaCheckInput, FormulationIngredient } from './formula/formula-checker.js';

export { validateLabel } from './label/label-validator.js';
export type { SupplementFactsInput } from './label/label-validator.js';

export { classifyClaim, FDA_DISCLAIMER } from './claims/claims-classifier.js';
export type { ClaimCheckInput } from './claims/claims-classifier.js';

export { normalizeIngredientName, parseAmount, normalizeUnit } from './utils/normalize.js';
export { cite, buildCitations } from './utils/citation-builder.js';

export { assessNDIEligibility } from './ndi/ndi-navigator.js';
export type { NDINavigatorInput, NDINavigatorResult, NDIChecklistStep } from './ndi/ndi-navigator.js';

export {
  scoreCGMPAudit,
  getCGMPSections,
  buildEmptyAuditInput,
  CGMP_SECTIONS,
} from './cgmp/cgmp-checker.js';
export type {
  CGMPAuditInput,
  CGMPAuditResult,
  CGMPSection,
  CGMPSectionId,
  CGMPCheckItem,
  CGMPSectionResult,
} from './cgmp/cgmp-checker.js';

export { checkProp65 } from './state/prop65-checker.js';
export type {
  Prop65CheckInput,
  Prop65CheckResult,
  Prop65ChemicalMatch,
} from './state/prop65-checker.js';

export { checkImportRequirements } from './import/import-checker.js';
export type {
  ImportCheckInput,
  ImportCheckResult,
  FSVPChecklistItem,
} from './import/import-checker.js';
