/**
 * Known ingredient interaction checker
 *
 * Flags clinically significant interactions between ingredients in the same
 * formulation. Based on published pharmacological data and FDA warning letters.
 */

import type { InteractionFlag } from '../types.js';

interface InteractionRule {
  ingredients: [string, string];
  severity: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';
  description: string;
  citation: string;
}

const KNOWN_INTERACTIONS: InteractionRule[] = [
  {
    ingredients: ['St. John\'s Wort', 'MAOIs'],
    severity: 'CRITICAL',
    description: 'St. John\'s Wort combined with MAOIs can cause serotonin syndrome — a potentially life-threatening condition.',
    citation: 'FDA Safety Alert (2000); Br J Clin Pharmacol. 2004;58(5):495-504',
  },
  {
    ingredients: ['St. John\'s Wort', '5-HTP'],
    severity: 'HIGH',
    description: 'Concurrent use of St. John\'s Wort and 5-HTP may increase risk of serotonin syndrome.',
    citation: 'FDA MedWatch; pharmacological serotonergic interaction',
  },
  {
    ingredients: ['Vitamin E', 'Warfarin'],
    severity: 'HIGH',
    description: 'High-dose Vitamin E (>400 IU/day) may potentiate anticoagulant effects and increase bleeding risk.',
    citation: 'Am J Clin Nutr. 2002;76(6):1151-56',
  },
  {
    ingredients: ['Kava', 'Alcohol'],
    severity: 'HIGH',
    description: 'Kava combined with alcohol increases hepatotoxicity risk and CNS depression.',
    citation: 'FDA Consumer Advisory on Kava (2002)',
  },
  {
    ingredients: ['Kava', 'Acetaminophen'],
    severity: 'HIGH',
    description: 'Kava may increase hepatotoxic risk when combined with acetaminophen.',
    citation: 'WHO Kava Monograph (2007)',
  },
  {
    ingredients: ['Iron', 'Calcium'],
    severity: 'MEDIUM',
    description: 'Calcium significantly reduces iron absorption when taken together. Recommend separating doses by 2+ hours.',
    citation: 'NIH ODS Iron Fact Sheet',
  },
  {
    ingredients: ['Iron', 'Zinc'],
    severity: 'MEDIUM',
    description: 'High-dose iron and zinc compete for absorption via shared transporters (DMT1).',
    citation: 'Am J Clin Nutr. 1994;59(3):646-51',
  },
  {
    ingredients: ['Vitamin D', 'Calcium'],
    severity: 'LOW',
    description: 'Very high combined doses of Vitamin D and Calcium can cause hypercalcemia. Monitor total intake.',
    citation: 'NIH ODS Vitamin D Fact Sheet; 21 CFR § 101.36',
  },
  {
    ingredients: ['Magnesium', 'Calcium'],
    severity: 'LOW',
    description: 'High magnesium intake may interfere with calcium absorption when taken simultaneously.',
    citation: 'NIH ODS Magnesium Fact Sheet',
  },
  {
    ingredients: ['Black Cohosh', 'Estrogen'],
    severity: 'HIGH',
    description: 'Black Cohosh has estrogenic activity and may interact with hormone therapies.',
    citation: 'FDA Advisory on Black Cohosh (2022)',
  },
  {
    ingredients: ['Ginkgo Biloba', 'Blood Thinners'],
    severity: 'HIGH',
    description: 'Ginkgo Biloba has anticoagulant properties and may increase bleeding risk when combined with blood-thinning agents.',
    citation: 'Neurology. 2002;58(9):1421-4',
  },
  {
    ingredients: ['Melatonin', 'Sedatives'],
    severity: 'MEDIUM',
    description: 'Melatonin may enhance CNS-depressant effects when combined with sedative compounds.',
    citation: 'NIH ODS Melatonin Fact Sheet',
  },
  {
    ingredients: ['Chromium Picolinate', 'Insulin'],
    severity: 'MEDIUM',
    description: 'Chromium picolinate may enhance insulin sensitivity; combined use may affect blood glucose control.',
    citation: 'Diabetes Care. 1997;20(3):475-7',
  },
  {
    ingredients: ['Ashwagandha', 'Thyroid Medications'],
    severity: 'MEDIUM',
    description: 'Ashwagandha may affect thyroid hormone levels; concurrent use with thyroid medications warrants monitoring.',
    citation: 'J Int Soc Sports Nutr. 2015;12:43',
  },
  {
    ingredients: ['Coenzyme Q10', 'Warfarin'],
    severity: 'MEDIUM',
    description: 'CoQ10 has vitamin K-like activity and may reduce warfarin anticoagulant effect.',
    citation: 'Ann Pharmacother. 1994;28(10):1219-21',
  },
];

export function checkInteractions(ingredientNames: string[]): InteractionFlag[] {
  const flags: InteractionFlag[] = [];
  const normalizedNames = ingredientNames.map((n) => n.toLowerCase());

  for (const rule of KNOWN_INTERACTIONS) {
    const [a, b] = rule.ingredients.map((n) => n.toLowerCase());

    const hasA = normalizedNames.some(
      (n) => n.includes(a) || a.includes(n),
    );
    const hasB = normalizedNames.some(
      (n) => n.includes(b) || b.includes(n),
    );

    if (hasA && hasB) {
      flags.push({
        ingredients: rule.ingredients,
        severity: rule.severity as InteractionFlag['severity'],
        description: rule.description,
        citation: rule.citation,
      });
    }
  }

  return flags;
}
