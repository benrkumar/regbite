/** Normalize an ingredient name for fuzzy matching */
export function normalizeIngredientName(name: string): string {
  return name
    .toLowerCase()
    .replace(/[()[\]]/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

/** Strip units and return numeric value */
export function parseAmount(value: string | number): number {
  if (typeof value === 'number') return value;
  const match = String(value).match(/[\d.]+/);
  return match ? parseFloat(match[0]) : 0;
}

/** Normalize unit strings to a canonical form */
export function normalizeUnit(unit: string): string {
  const u = unit.toLowerCase().trim();
  const MAP: Record<string, string> = {
    mcg: 'mcg', ug: 'mcg', µg: 'mcg',
    mg: 'mg',
    g: 'g', gm: 'g', gram: 'g', grams: 'g',
    iu: 'IU', 'i.u.': 'IU',
    'mcg rae': 'mcg RAE',
    'mcg dfe': 'mcg DFE',
    'mg ne': 'mg NE',
    '%': '%', 'percent': '%',
    'cfu': 'CFU', 'billion cfu': 'billion CFU',
  };
  return MAP[u] ?? unit;
}

/** Convert mg → mcg or g → mg for comparisons (returns value in base unit mcg) */
export function toMicrograms(amount: number, unit: string): number {
  switch (normalizeUnit(unit)) {
    case 'g':   return amount * 1_000_000;
    case 'mg':  return amount * 1_000;
    case 'mcg': return amount;
    default:    return amount;
  }
}
