/**
 * Claims classifier — structure/function vs disease claim detection
 *
 * FDA distinguishes three claim types for dietary supplements:
 *   - Structure/Function claims: describe how a nutrient affects body structure or function
 *     (e.g., "Vitamin C supports immune function") — permitted with required disclaimer
 *   - Health claims: FDA-authorized claims about a nutrient-disease relationship
 *     (e.g., "Calcium may reduce risk of osteoporosis") — must be pre-authorized
 *   - Disease claims: claim to diagnose, cure, treat, mitigate, or prevent a disease
 *     — PROHIBITED for dietary supplements (makes the product an unapproved drug)
 *
 * References:
 *   21 CFR § 101.93 — Structure/function claims
 *   21 CFR § 101.14 — Health claims
 *   FDA Guidance: "Guidance for Industry on Substantiation for Dietary Supplement Claims" (2009)
 *   FTC Act § 5 — Advertising substantiation requirement
 */

import type { ClaimValidationResult, CheckResult } from '../types.js';

// ── Disease claim patterns (50+ patterns) ─────────────────────────────────────

const DISEASE_CLAIM_PATTERNS: RegExp[] = [
  // Direct therapeutic verbs
  /\bcures?\b/i,
  /\btreat[s]?\b/i,
  /\bheals?\b/i,
  /\bprevents?\b/i,
  /\bdiagnoses?\b/i,
  /\bmitigates?\b/i,
  /\beliminate[s]?\b/i,
  /\breverse[s]?\b/i,
  /\bfight[s]?\b/i,
  /\bkill[s]?\b/i,

  // Disease names — oncology
  /\bcancer\b/i,
  /\btumor[s]?\b/i,
  /\bmalignant\b/i,
  /\bcarcinoma\b/i,
  /\bleukemia\b/i,
  /\blymphoma\b/i,
  /\bmelanoma\b/i,

  // Disease names — metabolic / cardiovascular
  /\bdiabetes\b/i,
  /\bdiabetic\b/i,
  /\binsulin resistance\b/i,
  /\bhypertension\b/i,
  /\bcoronary artery disease\b/i,
  /\batherosclerosis\b/i,
  /\bcongestive heart failure\b/i,
  /\bheart disease\b/i,
  /\bmyocardial infarction\b/i,
  /\bstroke\b/i,

  // Disease names — neurological
  /\balzheimer'?s?\b/i,
  /\bparkinson'?s?\b/i,
  /\bdementia\b/i,
  /\bmultiple sclerosis\b/i,
  /\bepilep[sy]+\b/i,
  /\bseizure[s]?\b/i,
  /\bneuropathy\b/i,

  // Disease names — musculoskeletal
  /\barthr[oi]tis\b/i,
  /\bosteoporosis\b/i,
  /\bosteoarthritis\b/i,
  /\brheumatoid\b/i,
  /\bfibromyalgia\b/i,

  // Disease names — respiratory / immune
  /\basthma\b/i,
  /\bcopd\b/i,
  /\bchronic obstructive\b/i,
  /\bautoimmune\b/i,
  /\blupus\b/i,
  /\bcrohn'?s?\b/i,
  /\bhiv\b|\baids\b/i,

  // Disease names — mental health
  /\bdepression\b/i,
  /\bschizophrenia\b/i,
  /\bbipolar\b/i,
  /\banxiety disorder\b/i,
  /\bptsd\b/i,

  // Disease names — other
  /\bhepatitis\b/i,
  /\bcirrhosis\b/i,
  /\bkidney disease\b/i,
  /\brenal failure\b/i,
  /\bulcer[s]?\b/i,
  /\birritable bowel\b/i,
  /\bceliac\b/i,
  /\bpsoriasis\b/i,
  /\beczema\b/i,
  /\bsepsis\b/i,
  /\binfection[s]?\b.*\bcure[s]?\b/i,
  /\bbacterial infection\b/i,
  /\bviral infection\b/i,

  // Drug-like language
  /\bclinically proven\b/i,
  /\bfda approved\b/i,
  /\bmedical(?:ally)? proven\b/i,
  /\bprescription(?:[-\s])?strength\b/i,
  /\bas effective as\s+\w+\s*(drug|medication|medicine)\b/i,
];

// ── Structure/function safe harbor patterns ────────────────────────────────────

const STRUCTURE_FUNCTION_PATTERNS: RegExp[] = [
  /\bsupport[s]?\b/i,
  /\bmaintain[s]?\b/i,
  /\bpromote[s]?\b/i,
  /\bhelp[s]?\b/i,
  /\bencourage[s]?\b/i,
  /\benhance[s]?\b/i,
  /\bboost[s]?\b/i,
  /\boptimize[s]?\b/i,
  /\bnourish(?:es|ing)?\b/i,
];

const FDA_DISCLAIMER =
  'These statements have not been evaluated by the Food and Drug Administration. This product is not intended to diagnose, treat, cure, or prevent any disease.';

// ── Claim rewrites ─────────────────────────────────────────────────────────────

const REWRITE_MAP: Record<string, string> = {
  'cures diabetes': 'may help maintain healthy blood sugar levels already within normal range',
  'treats cancer': 'may help support cellular health',
  'prevents heart disease': 'may support cardiovascular health and normal cholesterol levels already in the healthy range',
  'reduces hypertension': 'may help support blood pressure already within the normal range',
  'treats depression': 'may help support mood and emotional balance',
  'treats arthritis': 'may help support joint comfort and mobility',
  'prevents Alzheimer\'s': 'may help support cognitive function and memory',
  'treats infections': 'may help support the body\'s natural immune defenses',
  'cures': 'may help support',
  'treats': 'may help support',
  'prevents': 'may help support',
  'heals': 'may help support',
};

function generateSafeRewrite(claim: string): string {
  let safe = claim;
  for (const [bad, good] of Object.entries(REWRITE_MAP)) {
    safe = safe.replace(new RegExp(bad, 'gi'), good);
  }

  // Generic fallback if no specific replacement found
  const hasDiseaseWord = DISEASE_CLAIM_PATTERNS.some((p) => p.test(safe));
  if (hasDiseaseWord) {
    safe = safe
      .replace(/\bcure[s]?\b/gi, 'support')
      .replace(/\btreat[s]?\b/gi, 'support')
      .replace(/\bprevents?\b/gi, 'help support')
      .replace(/\bheals?\b/gi, 'support');
  }

  return safe !== claim ? `${safe} ${FDA_DISCLAIMER}` : '';
}

export interface ClaimCheckInput {
  claim: string;
  useAI?: boolean;
}

export function classifyClaim(input: ClaimCheckInput): ClaimValidationResult & { checks: CheckResult[] } {
  const { claim } = input;
  const checks: CheckResult[] = [];

  // ── Disease claim detection ──────────────────────────────────────────────
  const matchedDiseasePatterns = DISEASE_CLAIM_PATTERNS.filter((p) => p.test(claim));
  const isDiseaseClaim = matchedDiseasePatterns.length > 0;

  // ── Structure/function detection ────────────────────────────────────────
  const hasSFLanguage = STRUCTURE_FUNCTION_PATTERNS.some((p) => p.test(claim));

  // ── FDA disclaimer check ─────────────────────────────────────────────────
  const hasDisclaimer =
    /not intended to diagnose|not (?:been )?evaluated by the (?:food|fda)/i.test(claim);

  const classification: ClaimValidationResult['classification'] = isDiseaseClaim
    ? 'DISEASE'
    : hasSFLanguage
      ? 'STRUCTURE_FUNCTION'
      : 'HEALTH';

  const riskLevel: ClaimValidationResult['riskLevel'] = isDiseaseClaim
    ? 'CRITICAL'
    : classification === 'HEALTH'
      ? 'HIGH'
      : 'LOW';

  const suggestedRewrite = isDiseaseClaim ? generateSafeRewrite(claim) : undefined;

  // ── Build checks ─────────────────────────────────────────────────────────
  if (isDiseaseClaim) {
    const matched = matchedDiseasePatterns.map((p) => p.source).slice(0, 3).join(', ');
    checks.push({
      ruleId: 'CLAIM-001',
      ruleName: 'No disease claims',
      status: 'FAIL',
      severity: 'CRITICAL',
      message: `Disease claim detected in: "${claim}". Matched patterns: ${matched}. This claim implies the product diagnoses, treats, cures, or prevents a disease — which would make it an unapproved drug under the FD&C Act.`,
      remediation: suggestedRewrite
        ? `Rewrite as a structure/function claim: "${suggestedRewrite}"`
        : 'Rewrite using structure/function language (e.g., "supports", "helps maintain") and add FDA disclaimer.',
      regulatoryCitation: '21 CFR § 101.93; FD&C Act § 201(g)',
    });
  } else {
    checks.push({
      ruleId: 'CLAIM-001',
      ruleName: 'No disease claims',
      status: 'PASS',
      severity: 'LOW',
      message: `"${claim}" does not appear to make a disease claim.`,
      regulatoryCitation: '21 CFR § 101.93',
    });
  }

  // ── FDA disclaimer requirement ───────────────────────────────────────────
  if (classification === 'STRUCTURE_FUNCTION' && !hasDisclaimer) {
    checks.push({
      ruleId: 'CLAIM-002',
      ruleName: 'Required FDA disclaimer',
      status: 'FAIL',
      severity: 'HIGH',
      message: 'Structure/function claims require the FDA disclaimer on the label.',
      remediation: `Add the following disclaimer: "${FDA_DISCLAIMER}"`,
      regulatoryCitation: '21 CFR § 101.93(b)',
    });
  } else if (classification === 'STRUCTURE_FUNCTION') {
    checks.push({
      ruleId: 'CLAIM-002',
      ruleName: 'Required FDA disclaimer',
      status: 'PASS',
      severity: 'LOW',
      message: 'FDA disclaimer found.',
      regulatoryCitation: '21 CFR § 101.93(b)',
    });
  }

  // ── FTC substantiation ───────────────────────────────────────────────────
  const ftcRequired = !isDiseaseClaim; // disease claims are already outright invalid
  if (ftcRequired) {
    checks.push({
      ruleId: 'CLAIM-003',
      ruleName: 'FTC substantiation requirement',
      status: 'WARNING',
      severity: 'MEDIUM',
      message: `All advertising claims require "competent and reliable scientific evidence" under FTC Act § 5. Ensure this claim is supported by adequate clinical or scientific evidence.`,
      remediation: 'Maintain substantiation files (published studies, RCTs, or expert consensus) for all claims. See FTC Dietary Supplement Advertising Guide (2022).',
      regulatoryCitation: 'FTC Act § 5; FTC Dietary Supplement Advertising Guide (2022)',
    });
  }

  // ── Notification requirement ─────────────────────────────────────────────
  if (classification === 'STRUCTURE_FUNCTION') {
    checks.push({
      ruleId: 'CLAIM-004',
      ruleName: 'FDA notification requirement',
      status: 'WARNING',
      severity: 'MEDIUM',
      message: 'Structure/function claims must be submitted to FDA within 30 days of first marketing.',
      remediation: 'Notify FDA via the structure/function claim notification process before or within 30 days of first use.',
      regulatoryCitation: '21 CFR § 101.93(a)',
    });
  }

  return {
    claim,
    classification,
    isCompliant: !isDiseaseClaim,
    riskLevel,
    requiredDisclaimer: classification === 'STRUCTURE_FUNCTION' ? FDA_DISCLAIMER : undefined,
    ftcSubstantiationRequired: ftcRequired,
    enforcementPrecedents: [],
    suggestedRewrite,
    checks,
  };
}

export { FDA_DISCLAIMER };
