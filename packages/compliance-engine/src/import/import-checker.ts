/**
 * Import Intelligence — FDA Import Alert + FSMA FSVP checklist
 *
 * References:
 *   FDA Import Alerts IA 54-06 (adulterated dietary supplements)
 *   FDA Import Alerts IA 66-71 (misbranded dietary supplements)
 *   FSMA Final Rule: Foreign Supplier Verification Programs (21 CFR Part 1 Subpart L)
 *   21 CFR Part 1.500–1.514 — FSVP requirements
 */

import type { CheckResult } from '../types.js';

export interface ImportCheckInput {
  ingredientName?: string;
  supplierCountry: string;
  supplierName?: string;
  hasThirdPartyCertification?: boolean;
  hasCoA?: boolean;
  hasFSVPPlan?: boolean;
  hasSupplierAudit?: boolean;
  hasHazardAnalysis?: boolean;
}

export interface FSVPChecklistItem {
  id: string;
  requirement: string;
  description: string;
  citation: string;
  status: 'REQUIRED' | 'CONDITIONAL';
}

export interface ImportCheckResult {
  supplierCountry: string;
  riskLevel: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
  checks: CheckResult[];
  fsvpChecklist: FSVPChecklistItem[];
  importAlertRisk: boolean;
  keyRequirements: string[];
}

// High-risk countries for dietary supplement imports (based on FDA import alert history)
const HIGH_RISK_COUNTRIES = [
  'china', 'india', 'brazil', 'mexico', 'thailand', 'indonesia', 'vietnam',
  'peru', 'taiwan', 'philippines', 'pakistan', 'bangladesh',
];

const FSVP_CHECKLIST: FSVPChecklistItem[] = [
  {
    id: 'FSVP-001',
    requirement: 'Identify the FSVP importer of record',
    description: 'The FSVP importer is the US owner/consignee of the food at the time of US entry, or if no US owner/consignee exists, the US agent/representative of the foreign exporter.',
    citation: '21 CFR § 1.502',
    status: 'REQUIRED',
  },
  {
    id: 'FSVP-002',
    requirement: 'Conduct a hazard analysis for each ingredient/food',
    description: 'Evaluate known or reasonably foreseeable hazards for each ingredient: biological, chemical, physical, and radiological. Document the analysis.',
    citation: '21 CFR § 1.504',
    status: 'REQUIRED',
  },
  {
    id: 'FSVP-003',
    requirement: 'Evaluate foreign supplier performance and food safety',
    description: 'Review the foreign supplier\'s safety processes, compliance history, FDA inspection results, and any applicable food safety standards.',
    citation: '21 CFR § 1.505',
    status: 'REQUIRED',
  },
  {
    id: 'FSVP-004',
    requirement: 'Approve foreign suppliers before importing',
    description: 'Formally approve each foreign supplier based on hazard analysis and supplier evaluation. Document the approval decision and supporting rationale.',
    citation: '21 CFR § 1.506',
    status: 'REQUIRED',
  },
  {
    id: 'FSVP-005',
    requirement: 'Conduct or obtain foreign supplier audits',
    description: 'For high-risk suppliers or significant hazards, conduct onsite audits. Audits must be performed by qualified auditors. Frequency based on risk.',
    citation: '21 CFR § 1.506(e)',
    status: 'REQUIRED',
  },
  {
    id: 'FSVP-006',
    requirement: 'Obtain and review Certificates of Analysis (CoA)',
    description: 'Request CoAs for each lot/batch imported. CoAs must include testing results for identity, purity, and relevant contaminants (heavy metals, microbials).',
    citation: '21 CFR § 1.505(a)(1)',
    status: 'REQUIRED',
  },
  {
    id: 'FSVP-007',
    requirement: 'Verify compliance with US food safety standards',
    description: 'Ensure that the food or ingredient meets the same standards that would apply if it were produced domestically, or meets equivalent standards.',
    citation: '21 CFR § 1.502(a)',
    status: 'REQUIRED',
  },
  {
    id: 'FSVP-008',
    requirement: 'Maintain FSVP records for 2+ years',
    description: 'All FSVP records must be maintained for at least 2 years. Records must be available for FDA inspection within 24 hours and must be in English.',
    citation: '21 CFR § 1.510',
    status: 'REQUIRED',
  },
  {
    id: 'FSVP-009',
    requirement: 'Provide FSVP data entry at US port of entry',
    description: 'Importers must provide the FSVP importer\'s name, email, and DUNS number when submitting US Customs entry for food.',
    citation: '21 CFR § 1.509',
    status: 'REQUIRED',
  },
  {
    id: 'FSVP-010',
    requirement: 'Update FSVP when hazards or supplier performance changes',
    description: 'Review and update the FSVP at least every 3 years or when there is new information that indicates the FSVP may no longer ensure adequate supplier verification.',
    citation: '21 CFR § 1.508',
    status: 'REQUIRED',
  },
  {
    id: 'FSVP-011',
    requirement: 'Obtain third-party certification (if applicable)',
    description: 'FDA-accredited third-party certification is not required for most imports but may serve as qualified supplier verification activity for certain high-risk foods.',
    citation: '21 CFR Part 1 Subpart M',
    status: 'CONDITIONAL',
  },
];

export function checkImportRequirements(input: ImportCheckInput): ImportCheckResult {
  const checks: CheckResult[] = [];
  const country = input.supplierCountry.toLowerCase().trim();
  const isHighRisk = HIGH_RISK_COUNTRIES.some((c) => country.includes(c));
  const importAlertRisk = isHighRisk;

  let riskLevel: ImportCheckResult['riskLevel'] = isHighRisk ? 'HIGH' : 'MEDIUM';

  // Country risk check
  if (isHighRisk) {
    checks.push({
      ruleId: 'IMP-001',
      ruleName: 'High-risk supplier country',
      status: 'WARNING',
      severity: 'HIGH',
      message: `${input.supplierCountry} is a high-risk country for dietary supplement imports based on FDA import alert history. Enhanced verification is required.`,
      remediation: 'Conduct onsite supplier audit. Require ISO 22000 or NSF GMP certification. Test every lot for identity, purity, and contaminants.',
      regulatoryCitation: 'FDA Import Alerts IA 54-06; 21 CFR § 1.506(e)',
    });
  } else {
    checks.push({
      ruleId: 'IMP-001',
      ruleName: 'Supplier country risk',
      status: 'PASS',
      severity: 'LOW',
      message: `${input.supplierCountry} is not flagged as a high-risk country in FDA import alert data.`,
      regulatoryCitation: 'FDA Import Alert IA 54-06',
    });
  }

  // FSVP plan
  if (!input.hasFSVPPlan) {
    checks.push({
      ruleId: 'IMP-002',
      ruleName: 'FSMA FSVP Plan',
      status: 'FAIL',
      severity: 'CRITICAL',
      message: 'No FSVP (Foreign Supplier Verification Program) plan documented. Required for all dietary supplement imports under FSMA.',
      remediation: 'Develop a written FSVP for each foreign supplier. Complete the 10-item FSVP checklist below.',
      regulatoryCitation: '21 CFR Part 1 Subpart L (21 CFR § 1.500–1.514)',
    });
    riskLevel = 'CRITICAL';
  } else {
    checks.push({
      ruleId: 'IMP-002',
      ruleName: 'FSMA FSVP Plan',
      status: 'PASS',
      severity: 'LOW',
      message: 'FSVP plan is in place.',
      regulatoryCitation: '21 CFR § 1.502',
    });
  }

  // Hazard analysis
  if (!input.hasHazardAnalysis) {
    checks.push({
      ruleId: 'IMP-003',
      ruleName: 'Hazard analysis',
      status: 'FAIL',
      severity: 'CRITICAL',
      message: 'No hazard analysis documented for this ingredient/supplier.',
      remediation: 'Complete a written hazard analysis covering biological, chemical, physical, and radiological hazards before import.',
      regulatoryCitation: '21 CFR § 1.504',
    });
  } else {
    checks.push({
      ruleId: 'IMP-003',
      ruleName: 'Hazard analysis',
      status: 'PASS',
      severity: 'LOW',
      message: 'Hazard analysis documented.',
      regulatoryCitation: '21 CFR § 1.504',
    });
  }

  // Certificate of Analysis
  if (!input.hasCoA) {
    checks.push({
      ruleId: 'IMP-004',
      ruleName: 'Certificate of Analysis (CoA)',
      status: 'FAIL',
      severity: 'HIGH',
      message: 'No Certificate of Analysis available for this ingredient lot.',
      remediation: 'Require CoA from supplier for each lot. CoA must include identity, purity, potency, and contaminant testing results.',
      regulatoryCitation: '21 CFR § 1.505(a)(1); 21 CFR § 111.75(a)',
    });
  } else {
    checks.push({
      ruleId: 'IMP-004',
      ruleName: 'Certificate of Analysis (CoA)',
      status: 'PASS',
      severity: 'LOW',
      message: 'CoA present.',
      regulatoryCitation: '21 CFR § 1.505(a)(1)',
    });
  }

  // Supplier audit
  if (!input.hasSupplierAudit && isHighRisk) {
    checks.push({
      ruleId: 'IMP-005',
      ruleName: 'Foreign supplier audit',
      status: 'WARNING',
      severity: 'HIGH',
      message: `Supplier audit is strongly recommended for high-risk country imports from ${input.supplierCountry}.`,
      remediation: 'Schedule an onsite audit by a qualified food safety auditor within the next 12 months. Consider SMETA, ISO 22000, or NSF GMP audits.',
      regulatoryCitation: '21 CFR § 1.506(e)',
    });
  } else if (input.hasSupplierAudit) {
    checks.push({
      ruleId: 'IMP-005',
      ruleName: 'Foreign supplier audit',
      status: 'PASS',
      severity: 'LOW',
      message: 'Supplier audit completed.',
      regulatoryCitation: '21 CFR § 1.506(e)',
    });
  }

  // Third-party certification
  if (input.hasThirdPartyCertification) {
    checks.push({
      ruleId: 'IMP-006',
      ruleName: 'Third-party certification',
      status: 'PASS',
      severity: 'LOW',
      message: 'Third-party certification present. This strengthens your FSVP verification activities.',
      regulatoryCitation: '21 CFR Part 1 Subpart M',
    });
  }

  const keyRequirements = [
    'FSVP plan required for all dietary supplement imports under FSMA.',
    'Identity testing required for every incoming ingredient lot (21 CFR § 111.75(a)(1)).',
    'FSVP records must be retained for at least 2 years and available within 24 hours for FDA.',
    isHighRisk ? `${input.supplierCountry} is a high-risk country — enhanced verification (audits, lot testing) recommended.` : `Standard FSVP verification applies for ${input.supplierCountry}.`,
  ];

  return {
    supplierCountry: input.supplierCountry,
    riskLevel,
    checks,
    fsvpChecklist: FSVP_CHECKLIST,
    importAlertRisk,
    keyRequirements,
  };
}
