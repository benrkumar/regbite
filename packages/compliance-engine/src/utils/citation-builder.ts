export interface Citation {
  code: string;
  title: string;
  url: string;
}

const CITATIONS: Record<string, Citation> = {
  '21_CFR_101.36': {
    code: '21 CFR § 101.36',
    title: 'Nutrition labeling of dietary supplements',
    url: 'https://www.ecfr.gov/current/title-21/chapter-I/subchapter-B/part-101/section-101.36',
  },
  '21_CFR_101.9': {
    code: '21 CFR § 101.9',
    title: 'Nutrition labeling of food',
    url: 'https://www.ecfr.gov/current/title-21/chapter-I/subchapter-B/part-101/section-101.9',
  },
  '21_CFR_101.93': {
    code: '21 CFR § 101.93',
    title: 'Certain types of statements for dietary supplements',
    url: 'https://www.ecfr.gov/current/title-21/chapter-I/subchapter-B/part-101/section-101.93',
  },
  '21_CFR_101.54': {
    code: '21 CFR § 101.54',
    title: 'Nutrient content claims — fiber, vitamins, minerals',
    url: 'https://www.ecfr.gov/current/title-21/chapter-I/subchapter-B/part-101/section-101.54',
  },
  '21_CFR_111': {
    code: '21 CFR Part 111',
    title: 'Current Good Manufacturing Practice in Manufacturing, Packaging, Labeling, or Holding Operations for Dietary Supplements',
    url: 'https://www.ecfr.gov/current/title-21/chapter-I/subchapter-B/part-111',
  },
  DSHEA_1994: {
    code: 'DSHEA § 3 (21 U.S.C. § 321(ff))',
    title: 'Dietary Supplement Health and Education Act — definition of dietary supplement',
    url: 'https://www.fda.gov/food/dietary-supplements/dietary-supplement-health-and-education-act-1994',
  },
  DSHEA_NDI: {
    code: 'DSHEA § 8 (21 U.S.C. § 350b)',
    title: 'New dietary ingredient safety notification requirement',
    url: 'https://www.fda.gov/food/new-dietary-ingredients-ndi-notification-process',
  },
  FTC_ACT_5: {
    code: 'FTC Act § 5',
    title: 'Unfair or deceptive acts or practices',
    url: 'https://www.ftc.gov/legal-library/browse/statutes/federal-trade-commission-act',
  },
  FTC_DIETARY_GUIDANCE: {
    code: 'FTC Dietary Supplement Guidance (2022)',
    title: 'Dietary Supplements: An Advertising Guide for Industry',
    url: 'https://www.ftc.gov/business-guidance/resources/dietary-supplements-advertising-guide-industry',
  },
  FDA_DSIAL: {
    code: 'FDA Dietary Supplement Ingredient Advisory List',
    title: 'FDA Advisory List of Dietary Supplement Ingredients',
    url: 'https://www.fda.gov/food/dietary-supplement-ingredient-advisory-list/',
  },
};

export function cite(key: keyof typeof CITATIONS): string {
  return CITATIONS[key]?.code ?? key;
}

export function citeUrl(key: keyof typeof CITATIONS): string {
  return CITATIONS[key]?.url ?? '';
}

export function buildCitations(keys: (keyof typeof CITATIONS)[]): string[] {
  return keys.map((k) => CITATIONS[k]?.code ?? k);
}
