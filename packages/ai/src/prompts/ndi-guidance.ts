/**
 * NDI submission guidance prompt
 * Generates step-by-step NDI notification checklist for novel ingredients
 */

export interface NDIGuidanceInput {
  ingredientName: string;
  description: string;
  intendedUse: string;
  proposedDose?: string;
  manufacturingProcess?: string;
  existingResearch?: string;
}

export function buildNDIGuidancePrompt(input: NDIGuidanceInput): string {
  return `You are a US FDA regulatory affairs expert specializing in New Dietary Ingredient (NDI) notifications under DSHEA § 8 (21 U.S.C. § 350b).

Generate a comprehensive NDI notification checklist for the following ingredient.

## Ingredient Details

**Name:** ${input.ingredientName}
**Description:** ${input.description}
**Intended Use:** ${input.intendedUse}
${input.proposedDose ? `**Proposed Dose:** ${input.proposedDose}` : ''}
${input.manufacturingProcess ? `**Manufacturing Process:** ${input.manufacturingProcess}` : ''}
${input.existingResearch ? `**Existing Research:** ${input.existingResearch}` : ''}

## Required Output

Generate:

1. **NDI Eligibility Assessment** — Is this ingredient likely an NDI (marketed after Oct 15, 1994)?

2. **15-Step Submission Checklist** covering:
   - Ingredient identity and characterization data
   - Manufacturing and specification data
   - Recommended conditions of use
   - Safety information (human studies, animal studies, history of use)
   - Basis for concluding the ingredient is reasonably expected to be safe
   - Notification requirements (75-day timeline, FDA CFSAN submission)

3. **Documentation Gaps** — What evidence is missing for a successful notification?

4. **Timeline** — Realistic timeline from preparation to marketing (typically 4-8 months)

5. **Risk Assessment** — Likelihood of FDA raising safety concerns

Respond in structured JSON:
{
  "isNDI": boolean,
  "ndiReasoning": string,
  "submissionChecklist": [{ "step": number, "task": string, "required": boolean, "notes": string }],
  "documentationGaps": string[],
  "estimatedTimeline": string,
  "riskLevel": "LOW" | "MEDIUM" | "HIGH",
  "regulatoryCitations": string[]
}

All guidance must reference US FDA regulations only: DSHEA, 21 U.S.C. § 350b, FDA Draft Guidance on NDI Notifications (2016/2022).`;
}
