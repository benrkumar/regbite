/**
 * NDI Navigator — New Dietary Ingredient eligibility and submission guidance
 *
 * References:
 *   DSHEA § 8 (21 U.S.C. § 350b) — NDI notification requirement
 *   FDA Guidance: "New Dietary Ingredients in Dietary Supplements" (2016)
 *   21 CFR § 190.6 — NDI notification procedures
 */

import type { CheckResult } from '../types.js';
import { cite } from '../utils/citation-builder.js';

export interface NDINavigatorInput {
  ingredientName: string;
  casNumber?: string;
  /** Whether the ingredient was marketed in the US before October 15, 1994 */
  preMarketDSHEA?: boolean;
  /** Number of existing FDA NDI notifications for this ingredient */
  existingNDICount?: number;
  /** GRAS status */
  grasStatus?: string;
  /** FDA status */
  fdaStatus?: string;
  /** Whether the manufacturer has relevant safety studies */
  hasSafetyStudies?: boolean;
  /** Intended use/conditions of use */
  intendedUse?: string;
}

export interface NDIChecklistStep {
  stepNumber: number;
  title: string;
  description: string;
  status: 'REQUIRED' | 'OPTIONAL' | 'N_A';
  resourceUrl?: string;
  citation?: string;
}

export interface NDINavigatorResult {
  ingredientName: string;
  notificationRequired: boolean;
  eligibilityReason: string;
  riskLevel: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
  checks: CheckResult[];
  submissionChecklist: NDIChecklistStep[];
  estimatedReviewDays: number;
  keyFacts: string[];
}

const NDI_SUBMISSION_CHECKLIST: NDIChecklistStep[] = [
  {
    stepNumber: 1,
    title: 'Confirm NDI status',
    description: 'Verify the ingredient was not marketed in the US before October 15, 1994 (the DSHEA cut-off date). Check FDA\'s Dietary Supplement Ingredient Database and historical marketing records.',
    status: 'REQUIRED',
    citation: 'DSHEA § 8(a)',
  },
  {
    stepNumber: 2,
    title: 'Search existing NDI notifications',
    description: 'Search FDA\'s NDI Notification Database to see if a prior manufacturer has already submitted a notification. You may be able to rely on an existing notification if the conditions of use are the same.',
    status: 'REQUIRED',
    resourceUrl: 'https://www.fda.gov/food/dietary-supplements/new-dietary-ingredient-notification-process',
    citation: '21 CFR § 190.6(a)',
  },
  {
    stepNumber: 3,
    title: 'Evaluate GRAS status',
    description: 'Determine whether the ingredient qualifies as Generally Recognized As Safe (GRAS) under 21 CFR § 182 or § 184. GRAS substances do not require NDI notification.',
    status: 'REQUIRED',
    citation: '21 CFR § 170.30',
  },
  {
    stepNumber: 4,
    title: 'Conduct safety review',
    description: 'Compile safety data including: acute and chronic toxicity studies, human clinical data, historical use data, dose-response information, and any known adverse effects.',
    status: 'REQUIRED',
    citation: 'FDA NDI Guidance (2016)',
  },
  {
    stepNumber: 5,
    title: 'Establish conditions of use',
    description: 'Define the specific conditions under which the ingredient is safe: intended population, dosage form, serving level per day, frequency of use, and intended physical or physiological effect.',
    status: 'REQUIRED',
    citation: '21 CFR § 190.6(b)(2)',
  },
  {
    stepNumber: 6,
    title: 'Prepare safety narrative',
    description: 'Write a comprehensive safety narrative explaining why, under the stated conditions of use, the ingredient will reasonably be expected to be safe. Include evaluation methodology and data interpretation.',
    status: 'REQUIRED',
    citation: 'FDA NDI Guidance (2016), Section IV',
  },
  {
    stepNumber: 7,
    title: 'Compile identity documentation',
    description: 'Document full chemical identity: common name, Latin binomial (if botanical), CAS number, part of plant used, extraction process, chemical characterization, and specification sheet.',
    status: 'REQUIRED',
    citation: '21 CFR § 190.6(b)(1)',
  },
  {
    stepNumber: 8,
    title: 'Assess manufacturing process',
    description: 'Document how the ingredient is manufactured, including: source material, processing steps, solvents used (if any), concentration method, and final form. Any significant structural changes may affect NDI status.',
    status: 'REQUIRED',
    citation: 'FDA NDI Guidance (2016), Section V.A',
  },
  {
    stepNumber: 9,
    title: 'Prepare contaminant/purity data',
    description: 'Provide analytical testing data for heavy metals, pesticide residues, microbial contaminants, solvent residues, and any ingredient-specific contaminants of concern.',
    status: 'REQUIRED',
    citation: '21 CFR Part 111',
  },
  {
    stepNumber: 10,
    title: 'Submit notification to FDA',
    description: 'Submit the NDI notification to FDA via the CFSAN Submission Portal at least 75 days before marketing. The notification must be in English and include all required elements under 21 CFR § 190.6.',
    status: 'REQUIRED',
    resourceUrl: 'https://www.fda.gov/food/dietary-supplements/submitting-ndi-notification',
    citation: '21 CFR § 190.6; DSHEA § 8(a)(2)',
  },
  {
    stepNumber: 11,
    title: 'Wait 75-day review period',
    description: 'FDA has 75 days from receipt to respond. Do not market the dietary supplement until the 75-day period has elapsed. FDA may respond with a "no objection" letter or objections.',
    status: 'REQUIRED',
    citation: 'DSHEA § 8(a)(2)',
  },
  {
    stepNumber: 12,
    title: 'Address FDA objections (if any)',
    description: 'If FDA objects to your notification, you must resolve those objections before marketing. Common objections include insufficient safety data and inadequate identity documentation.',
    status: 'OPTIONAL',
    citation: 'FDA NDI Guidance (2016), Section VII',
  },
  {
    stepNumber: 13,
    title: 'Maintain notification records',
    description: 'Keep copies of the submission, FDA correspondence, and all supporting safety data. These records are subject to FDA inspection under cGMP regulations.',
    status: 'REQUIRED',
    citation: '21 CFR § 111.95',
  },
  {
    stepNumber: 14,
    title: 'Update notification if conditions change',
    description: 'If you change the conditions of use (e.g., increase the serving level, add a new population), you must submit a new or amended notification before marketing under the new conditions.',
    status: 'REQUIRED',
    citation: 'FDA NDI Guidance (2016), Section VIII',
  },
  {
    stepNumber: 15,
    title: 'Register in FDA DSAR (recommended)',
    description: 'Consider registering in the Dietary Supplement Adverse Events Reporting (DSAR) system to monitor post-market safety signals for your ingredient.',
    status: 'OPTIONAL',
    resourceUrl: 'https://www.fda.gov/food/dietary-supplements/reporting-serious-adverse-events',
    citation: '21 U.S.C. § 342(f)(1)(C)',
  },
];

export function assessNDIEligibility(input: NDINavigatorInput): NDINavigatorResult {
  const checks: CheckResult[] = [];
  let notificationRequired = true;
  let eligibilityReason = '';
  let riskLevel: NDINavigatorResult['riskLevel'] = 'HIGH';

  // ── BANNED check ─────────────────────────────────────────────────────────────
  if (input.fdaStatus === 'BANNED') {
    checks.push({
      ruleId: 'NDI-001',
      ruleName: 'FDA Marketing Prohibition',
      status: 'FAIL',
      severity: 'CRITICAL',
      message: `${input.ingredientName} is banned by FDA and cannot be marketed as a dietary supplement ingredient regardless of NDI status.`,
      remediation: 'This ingredient cannot be used in dietary supplements marketed in the US. Select a permitted alternative.',
      regulatoryCitation: 'FD&C Act § 402(f)',
    });
    notificationRequired = false;
    eligibilityReason = 'Ingredient is banned by FDA — NDI notification is moot; ingredient cannot be marketed.';
    riskLevel = 'CRITICAL';
    return { ingredientName: input.ingredientName, notificationRequired, eligibilityReason, riskLevel, checks, submissionChecklist: [], estimatedReviewDays: 0, keyFacts: ['FDA has banned this ingredient for use in dietary supplements.'] };
  }

  // ── Pre-DSHEA (grandfathered) check ──────────────────────────────────────────
  if (input.preMarketDSHEA === true) {
    notificationRequired = false;
    eligibilityReason = 'Ingredient was marketed as a dietary supplement in the US before October 15, 1994 (pre-DSHEA). No NDI notification required.';
    riskLevel = 'LOW';
    checks.push({
      ruleId: 'NDI-002',
      ruleName: 'Pre-DSHEA Grandfathered Status',
      status: 'PASS',
      severity: 'LOW',
      message: `${input.ingredientName} appears to qualify for pre-DSHEA grandfathered status. NDI notification is not required.`,
      remediation: 'Maintain documentation proving marketing prior to October 15, 1994 (e.g., historical catalogs, sales records, published literature).',
      regulatoryCitation: 'DSHEA § 8(a); 21 U.S.C. § 350b(a)',
    });
  }
  // ── GRAS check ───────────────────────────────────────────────────────────────
  else if (input.grasStatus === 'GRAS' || input.grasStatus === 'SELF_AFFIRMED') {
    notificationRequired = false;
    eligibilityReason = 'Ingredient is Generally Recognized As Safe (GRAS). GRAS substances do not require NDI notification.';
    riskLevel = 'LOW';
    checks.push({
      ruleId: 'NDI-003',
      ruleName: 'GRAS Exemption',
      status: 'PASS',
      severity: 'LOW',
      message: `${input.ingredientName} has GRAS status — not subject to NDI notification requirement.`,
      remediation: 'Maintain GRAS documentation (FDA GRAS Notice or self-affirmed GRAS dossier).',
      regulatoryCitation: '21 CFR §§ 170.30, 182, 184',
    });
  }
  // ── Existing NDI notification ────────────────────────────────────────────────
  else if ((input.existingNDICount ?? 0) > 0) {
    notificationRequired = false;
    eligibilityReason = `${input.existingNDICount} existing NDI notification(s) found. You may be able to rely on an existing notification if your conditions of use are the same or less restrictive.`;
    riskLevel = 'LOW';
    checks.push({
      ruleId: 'NDI-004',
      ruleName: 'Existing NDI Notification',
      status: 'PASS',
      severity: 'LOW',
      message: `${input.existingNDICount} prior NDI notification(s) exist for ${input.ingredientName}. Review whether your conditions of use are covered.`,
      remediation: 'Verify that your intended serving level, population, and dosage form are within the scope of the existing notification. If not, you must file your own notification.',
      regulatoryCitation: '21 CFR § 190.6(a)',
    });
  }
  // ── NDI notification required ────────────────────────────────────────────────
  else {
    notificationRequired = true;
    eligibilityReason = `${input.ingredientName} appears to be a New Dietary Ingredient requiring a 75-day pre-market notification to FDA before marketing.`;
    riskLevel = input.hasSafetyStudies ? 'MEDIUM' : 'HIGH';

    checks.push({
      ruleId: 'NDI-005',
      ruleName: 'NDI Notification Required',
      status: 'FAIL',
      severity: input.hasSafetyStudies ? 'HIGH' : 'CRITICAL',
      message: `${input.ingredientName} requires an NDI notification submitted at least 75 days before first marketing.`,
      remediation: 'Complete the 15-step submission checklist below. Submit via the CFSAN Submission Portal at least 75 days before your intended launch date.',
      regulatoryCitation: 'DSHEA § 8(a); 21 CFR § 190.6',
    });

    if (!input.hasSafetyStudies) {
      checks.push({
        ruleId: 'NDI-006',
        ruleName: 'Safety Data Required',
        status: 'WARNING',
        severity: 'HIGH',
        message: 'No safety studies indicated. FDA requires evidence that the ingredient will "reasonably be expected to be safe."',
        remediation: 'Commission or source toxicology studies, human clinical safety data, or historical use documentation before filing.',
        regulatoryCitation: 'FDA NDI Guidance (2016); DSHEA § 8(a)(1)',
      });
    }
  }

  // ── Safety studies check (universal) ─────────────────────────────────────────
  if (input.hasSafetyStudies === false && notificationRequired) {
    riskLevel = 'HIGH';
  }

  // ── Adverse status checks ─────────────────────────────────────────────────────
  if (input.fdaStatus === 'RESTRICTED') {
    checks.push({
      ruleId: 'NDI-007',
      ruleName: 'FDA Restricted Status',
      status: 'WARNING',
      severity: 'HIGH',
      message: `${input.ingredientName} has FDA-restricted status. Marketing may be permitted only under specific conditions.`,
      remediation: 'Review FDA restriction conditions. Obtain legal review before proceeding with marketing or NDI submission.',
      regulatoryCitation: 'FD&C Act § 402(f)(1)(A)',
    });
    if (riskLevel === 'LOW' || riskLevel === 'MEDIUM') riskLevel = 'HIGH';
  }

  if (input.fdaStatus === 'ADVISORY') {
    checks.push({
      ruleId: 'NDI-008',
      ruleName: 'FDA Advisory Notice',
      status: 'WARNING',
      severity: 'MEDIUM',
      message: `FDA has issued an advisory notice for ${input.ingredientName}. Review the advisory before marketing.`,
      remediation: 'Consult the FDA Dietary Supplement Ingredient Advisory List and include the advisory context in your safety narrative.',
      regulatoryCitation: cite('FDA_NDI'),
    });
  }

  const checklist = notificationRequired
    ? NDI_SUBMISSION_CHECKLIST
    : NDI_SUBMISSION_CHECKLIST.filter((s) => s.stepNumber <= 3);

  const keyFacts = buildKeyFacts(input, notificationRequired);

  return {
    ingredientName: input.ingredientName,
    notificationRequired,
    eligibilityReason,
    riskLevel,
    checks,
    submissionChecklist: checklist,
    estimatedReviewDays: notificationRequired ? 75 : 0,
    keyFacts,
  };
}

function buildKeyFacts(input: NDINavigatorInput, required: boolean): string[] {
  const facts: string[] = [];
  if (required) {
    facts.push('NDI notification must be submitted at least 75 days before first marketing (21 CFR § 190.6).');
    facts.push('Failure to submit an NDI notification before marketing renders the supplement adulterated under FD&C Act § 402(f)(1)(B).');
    facts.push('FDA will send an acknowledgment letter within 30 days of receipt.');
    facts.push('If FDA does not object within 75 days, you may proceed to market (but FDA may still take action later).');
  } else {
    facts.push('No NDI notification required based on your inputs. Keep documentation supporting this determination.');
    if (input.preMarketDSHEA) {
      facts.push('Maintain records proving pre-October 15, 1994 US marketing in case of FDA inquiry.');
    }
  }
  facts.push('NDI status is ingredient-specific AND conditions-of-use-specific. Changing the serving level or intended population may require a new notification.');
  return facts;
}
