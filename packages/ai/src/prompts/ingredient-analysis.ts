/**
 * FDA ingredient analysis prompt — US-specific
 *
 * Analyzes a dietary supplement ingredient under the US regulatory framework:
 * DSHEA (21 U.S.C. § 321(ff)), 21 CFR Part 111 cGMP, and FDA enforcement history.
 *
 * This prompt is purpose-built for US FDA regulations and has no relationship
 * to any India/FSSAI regulatory framework.
 */

import type { RetrievedDocument } from '../rag/retriever.js';

export interface IngredientAnalysisInput {
  ingredientName: string;
  casNumber?: string;
  amount?: number;
  unit?: string;
  productType?: string;
  context?: RetrievedDocument[];
}

export function buildIngredientAnalysisPrompt(input: IngredientAnalysisInput): string {
  const contextSection =
    input.context && input.context.length > 0
      ? `\n## Relevant FDA Regulatory Context\n\n${input.context
          .map(
            (doc, i) =>
              `[${i + 1}] **${doc.title}** (${doc.source})\n${doc.content.slice(0, 400)}...`,
          )
          .join('\n\n')}`
      : '';

  const dosageSection =
    input.amount && input.unit
      ? `\n**Proposed Dose:** ${input.amount} ${input.unit} per serving`
      : '';

  return `You are a US dietary supplement regulatory compliance expert with expertise in FDA/DSHEA regulations.

Analyze the following ingredient for use in a dietary supplement marketed in the United States.

## Ingredient Information

**Name:** ${input.ingredientName}${input.casNumber ? `\n**CAS Number:** ${input.casNumber}` : ''}${dosageSection}${input.productType ? `\n**Product Type:** ${input.productType}` : ''}
${contextSection}

## Analysis Required

Provide a structured analysis covering:

1. **FDA Regulatory Status** — Is this ingredient lawful for use in dietary supplements under DSHEA (21 U.S.C. § 321(ff))? Is it GRAS, an approved food additive, or does it require an NDI notification?

2. **New Dietary Ingredient (NDI) Assessment** — Was this ingredient marketed in the US as a dietary supplement before October 15, 1994 (DSHEA cutoff)? If not, is an NDI notification required under 21 U.S.C. § 350b?

3. **Safety Profile** — What does the published scientific literature say about safety at the proposed dose? Are there NIH Tolerable Upper Intake Level concerns? Any FDA safety advisories?

4. **Warning Letter History** — Has this ingredient been cited in FDA warning letters? What were the violations?

5. **cGMP Considerations** — Are there any known quality/manufacturing issues (21 CFR Part 111)?

6. **Prop 65 Exposure** — Is this ingredient on California Proposition 65? If so, what is the safe harbor level?

7. **Compliance Recommendation** — Overall assessment: PERMITTED / RESTRICTED / ADVISORY / BANNED, with specific action items.

## Output Format

Respond in structured JSON:
{
  "overallStatus": "PERMITTED" | "RESTRICTED" | "ADVISORY" | "BANNED",
  "ndiRequired": boolean,
  "ndiReasoning": string,
  "safetyRating": "LOW_RISK" | "MODERATE_RISK" | "HIGH_RISK" | "PROHIBITED",
  "keyFindings": string[],
  "actionItems": string[],
  "regulatoryCitations": string[],
  "confidenceLevel": "HIGH" | "MEDIUM" | "LOW"
}

Base all analysis on US FDA regulations: DSHEA (21 U.S.C. § 321(ff)), 21 CFR §§ 101.36, 101.93, Part 111. Do not reference any foreign regulations.`;
}
