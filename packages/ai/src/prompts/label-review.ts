/**
 * Label review prompt — 21 CFR § 101.36 Supplement Facts analysis
 */

export interface LabelReviewInput {
  extractedText: string;
  productName?: string;
}

export function buildLabelReviewPrompt(input: LabelReviewInput): string {
  return `You are a US dietary supplement label compliance expert with expertise in 21 CFR § 101.36 and FDA labeling requirements.

Review the following text extracted from a dietary supplement label.

## Extracted Label Text

${input.extractedText.slice(0, 4000)}

${input.productName ? `**Product:** ${input.productName}` : ''}

## Review Task

Extract structured label data and identify compliance issues under 21 CFR § 101.36.

Check for:
1. **Supplement Facts panel completeness** — serving size, servings per container, all required nutrients
2. **Statement of Identity** — must include "Dietary Supplement"
3. **Manufacturer/distributor information** — required under 21 CFR § 101.5
4. **Net quantity statement** — required on principal display panel
5. **Allergen declarations** — FALCPA/FASTER Act requirements for Big 9 allergens
6. **Proprietary blends** — must declare total weight and list ingredients in descending order
7. **FDA disclaimer** — required for structure/function claims (21 CFR § 101.93(b))
8. **Other ingredients** — must appear outside Supplement Facts box

## Output Format

Respond in structured JSON:
{
  "extractedData": {
    "productName": string | null,
    "servingSize": string | null,
    "servingsPerContainer": string | null,
    "identityStatement": string | null,
    "manufacturerInfo": string | null,
    "netQuantity": string | null,
    "allergens": string[],
    "hasDisclaimers": string[],
    "nutrients": [{ "name": string, "amount": number, "unit": string, "dvPercent": number | null }],
    "otherIngredients": string[],
    "hasLotCode": boolean,
    "hasExpirationDate": boolean
  },
  "complianceIssues": [{ "field": string, "issue": string, "severity": "CRITICAL" | "HIGH" | "MEDIUM" | "LOW", "citation": string }],
  "overallRisk": "LOW" | "MEDIUM" | "HIGH" | "CRITICAL"
}`;
}
