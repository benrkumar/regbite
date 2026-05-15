/**
 * Claims classification prompt — US FDA/FTC framework
 *
 * Classifies ambiguous claims that did not definitively match structure/function
 * or disease claim patterns in the rules engine. Claude Sonnet provides
 * nuanced classification for edge cases.
 *
 * Regulatory basis: 21 CFR § 101.93, FTC Act § 5, FDA Guidance (2009, 2022)
 */

import type { RetrievedDocument } from '../rag/retriever.js';

export interface ClaimsClassificationInput {
  claim: string;
  productType?: string;
  ingredientContext?: string;
  enforcementContext?: RetrievedDocument[];
}

export function buildClaimsClassificationPrompt(input: ClaimsClassificationInput): string {
  const enforcementSection =
    input.enforcementContext && input.enforcementContext.length > 0
      ? `\n## FDA Enforcement Precedents\n\n${input.enforcementContext
          .slice(0, 3)
          .map((doc) => `- **${doc.title}:** ${doc.content.slice(0, 300)}`)
          .join('\n')}`
      : '';

  return `You are a US dietary supplement regulatory expert specializing in FDA claim classifications and FTC advertising compliance.

## Claim to Classify

"${input.claim}"

${input.productType ? `**Product Type:** ${input.productType}` : ''}
${input.ingredientContext ? `**Active Ingredients:** ${input.ingredientContext}` : ''}
${enforcementSection}

## Classification Framework

Under US law, dietary supplement claims fall into these categories:

**1. Structure/Function Claim (PERMITTED with disclaimer)**
- Describes how a nutrient or dietary ingredient affects body structure or function
- Examples: "Vitamin C supports immune function", "Calcium helps build strong bones"
- Requires: FDA disclaimer, FDA notification within 30 days (21 CFR § 101.93)
- Test: Does it describe a structure or function of the body, NOT a disease?

**2. Health Claim (PERMITTED only if FDA-authorized)**
- Characterizes the relationship between a nutrient and a disease or health condition
- Must be either FDA-approved or qualified with FDA-approved language
- Examples: "Adequate calcium may reduce risk of osteoporosis"

**3. Disease Claim (PROHIBITED — makes product an unapproved drug)**
- Claims to diagnose, cure, treat, mitigate, or prevent a specific disease
- Examples: "Treats cancer", "Cures diabetes", "Prevents Alzheimer's"
- Test: Would the average consumer interpret this as a claim that the product:
  (a) Diagnoses, treats, mitigates, cures, or prevents a disease?
  (b) Affects a diseased body structure or function?

**4. Nutrient Content Claim (PERMITTED under 21 CFR § 101.54)**
- Characterizes the level of a nutrient in a product
- Examples: "High in Vitamin C", "Excellent source of calcium"

## Task

1. Classify this claim into one of the four categories above
2. Assess whether it is compliant as written
3. If it is a disease claim or otherwise non-compliant, provide a compliant rewrite as a structure/function claim
4. Identify which FDA/FTC regulation applies
5. Note any relevant FDA enforcement precedents from the context provided

## Output Format

Respond in structured JSON only:
{
  "classification": "STRUCTURE_FUNCTION" | "HEALTH" | "DISEASE" | "NUTRIENT_CONTENT",
  "isCompliant": boolean,
  "riskLevel": "LOW" | "MEDIUM" | "HIGH" | "CRITICAL",
  "reasoning": string,
  "suggestedRewrite": string | null,
  "requiredDisclaimer": string | null,
  "ftcSubstantiationRequired": boolean,
  "regulatoryCitations": string[],
  "enforcementPrecedents": string[]
}

Analyze strictly under US FDA (21 CFR) and FTC (FTC Act § 5) frameworks only.`;
}
