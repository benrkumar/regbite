const MODULES = [
  {
    id: 'ingredient',
    name: 'Ingredient Checker',
    file: 'packages/compliance-engine/src/ingredient/ingredient-checker.ts',
    description: 'Checks FDA status, GRAS standing, NDI requirement, prop65, and upper intake level for individual ingredients.',
    rules: ['FDA status (PERMITTED/GRAS/RESTRICTED/BANNED/ADVISORY)', 'NDI notification requirement', 'NIH upper intake level comparison', 'Prop 65 listing'],
    citation: 'DSHEA; 21 CFR Parts 101, 170–189; GRAS 21 CFR §§ 182–186',
  },
  {
    id: 'formula',
    name: 'Formula Checker',
    file: 'packages/compliance-engine/src/formula/formula-checker.ts',
    description: 'Runs per-ingredient checks across a full formula and aggregates a compliance score.',
    rules: ['Per-ingredient FDA/GRAS/NDI checks', 'NIH UL dosage comparison', 'Known ingredient interaction flags', 'Aggregate penalty-based scoring'],
    citation: '21 CFR Part 111; NIH DRIs; DSHEA',
  },
  {
    id: 'label',
    name: 'Label Validator (21 CFR 101.36)',
    file: 'packages/compliance-engine/src/label/label-validator.ts',
    description: '10 check functions covering all Supplement Facts panel requirements.',
    rules: [
      'Serving size format (21 CFR § 101.9)',
      '%DV accuracy for 13 nutrients (21 CFR § 101.36)',
      'Proprietary blend total weight + individual listing',
      'Big 9 allergens (FALCPA / FASTER Act)',
      'Other ingredients list order',
      'Identity statement format',
      'Manufacturer/distributor address',
      'Lot code + expiration requirements',
    ],
    citation: '21 CFR § 101.36; FALCPA (21 USC § 343)',
  },
  {
    id: 'claims',
    name: 'Claims Classifier',
    file: 'packages/compliance-engine/src/claims/claims-classifier.ts',
    description: 'Pattern matching + Claude AI classification of marketing claims.',
    rules: [
      '50+ disease claim patterns (regex)',
      'Structure/function vs. disease claim classification',
      'Required FDA disclaimer check',
      'FTC substantiation standard flagging',
      'Safe rewrite generation (Claude Sonnet)',
    ],
    citation: '21 CFR § 101.93; DSHEA § 6; FTC Policy Statement',
  },
  {
    id: 'ndi',
    name: 'NDI Navigator',
    file: 'packages/compliance-engine/src/ndi/ndi-navigator.ts',
    description: 'DSHEA § 8 eligibility determination + 15-step submission checklist.',
    rules: [
      'Pre-DSHEA grandfathered (before Oct 15, 1994)',
      'GRAS exemption check',
      'Existing NDI notification lookup',
      '15-step DSHEA § 8 checklist',
    ],
    citation: 'DSHEA § 8; 21 CFR § 190.6',
  },
  {
    id: 'cgmp',
    name: 'cGMP Readiness',
    file: 'packages/compliance-engine/src/cgmp/cgmp-checker.ts',
    description: '7-section scored audit covering all of 21 CFR Part 111.',
    rules: [
      'Personnel (§ 111.8–111.16)',
      'Physical plant (§ 111.15–111.27)',
      'Equipment (§ 111.27–111.35)',
      'Production & process controls (§ 111.65–111.95)',
      'Quality control (§ 111.105–111.140)',
      'Laboratory operations (§ 111.315–111.370)',
      'Complaint handling (§ 111.560–111.605)',
    ],
    citation: '21 CFR Part 111',
  },
  {
    id: 'prop65',
    name: 'Prop 65 Checker',
    file: 'packages/compliance-engine/src/state/prop65-checker.ts',
    description: 'Cross-references ingredients against OEHHA Prop 65 chemical list.',
    rules: ['CAS number exact match', 'Chemical name fuzzy match (insensitive)', 'Carcinogen vs. reproductive toxicant classification', 'Warning language generation'],
    citation: 'Cal. Health & Safety Code § 25249.5; OEHHA Title 27, CCR § 25603',
  },
  {
    id: 'import',
    name: 'Import Checker',
    file: 'packages/compliance-engine/src/import/import-checker.ts',
    description: 'FDA Import Alert risk by supplier country + 11-item FSVP checklist.',
    rules: [
      'High-risk country detection (12 countries)',
      'FSVP plan presence check',
      'Hazard analysis documentation',
      'Certificate of Analysis (CoA) requirement',
      'Supplier audit recommendation (high-risk)',
      'Third-party certification credit',
    ],
    citation: '21 CFR Part 1 Subpart L (§§ 1.500–1.514); FDA Import Alert IA 54-06',
  },
];

const SCORING = [
  { severity: 'CRITICAL', deduction: -10, color: 'text-red-400' },
  { severity: 'HIGH', deduction: -6, color: 'text-orange-400' },
  { severity: 'MEDIUM', deduction: -3, color: 'text-yellow-400' },
  { severity: 'LOW', deduction: -1, color: 'text-gray-400' },
];

export default function ComplianceRulesPage() {
  return (
    <div className="max-w-5xl">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-white">Compliance Rules</h1>
        <p className="text-sm text-gray-500 mt-1">All compliance rule modules and their regulatory sources.</p>
      </div>

      {/* Scoring model */}
      <div className="rounded-lg bg-gray-900 border border-gray-800 p-5 mb-6">
        <p className="text-sm font-semibold text-white mb-3">Scoring Model</p>
        <p className="text-xs text-gray-400 mb-3">Penalty-based: starts at 100, deductions per FAIL. WARNING = ½ deduction. Floor at 0.</p>
        <div className="flex gap-6">
          {SCORING.map((s) => (
            <div key={s.severity}>
              <p className={`text-base font-bold ${s.color}`}>{s.deduction}</p>
              <p className="text-xs text-gray-500">{s.severity}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Rule modules */}
      <div className="space-y-3">
        {MODULES.map((mod) => (
          <div key={mod.id} className="rounded-lg bg-gray-900 border border-gray-800 p-5">
            <div className="flex items-start gap-4">
              <div className="flex-1">
                <p className="text-sm font-semibold text-white">{mod.name}</p>
                <p className="text-xs font-mono text-gray-600 mt-0.5">{mod.file}</p>
                <p className="text-xs text-gray-400 mt-2">{mod.description}</p>
              </div>
            </div>
            <div className="mt-3 grid grid-cols-2 gap-1">
              {mod.rules.map((rule) => (
                <p key={rule} className="text-xs text-gray-500">· {rule}</p>
              ))}
            </div>
            <p className="mt-3 text-xs font-mono text-gray-600">{mod.citation}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
