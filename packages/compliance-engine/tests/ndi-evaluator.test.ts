import { describe, it, expect } from 'vitest';
import { evaluateNDIRequirement } from '../src/ingredient/ndi-evaluator.js';

describe('NDI evaluator', () => {
  it('does not require NDI for grandfathered ingredients', () => {
    const result = evaluateNDIRequirement({
      dsheaGrandfathered: true,
      ndiNotificationsCount: 0,
      grasStatus: 'UNKNOWN',
      fdaStatus: 'PERMITTED',
      ingredientName: 'Vitamin C',
    });
    expect(result.ndiRequired).toBe(false);
    expect(result.exemption).toMatch(/Pre-DSHEA/);
  });

  it('does not require NDI when GRAS', () => {
    const result = evaluateNDIRequirement({
      dsheaGrandfathered: false,
      ndiNotificationsCount: 0,
      grasStatus: 'FDA_AFFIRMED',
      fdaStatus: 'PERMITTED',
      ingredientName: 'Lecithin',
    });
    expect(result.ndiRequired).toBe(false);
    expect(result.exemption).toMatch(/GRAS/);
  });

  it('does not require NDI when existing notifications exist', () => {
    const result = evaluateNDIRequirement({
      dsheaGrandfathered: false,
      ndiNotificationsCount: 3,
      grasStatus: 'UNKNOWN',
      fdaStatus: 'PERMITTED',
      ingredientName: 'Quercetin',
    });
    expect(result.ndiRequired).toBe(false);
    expect(result.reasoning).toMatch(/3 existing NDI/);
  });

  it('requires NDI for novel ingredients with no history', () => {
    const result = evaluateNDIRequirement({
      dsheaGrandfathered: false,
      ndiNotificationsCount: 0,
      grasStatus: 'UNKNOWN',
      fdaStatus: 'UNKNOWN',
      ingredientName: 'Novel botanical extract',
    });
    expect(result.ndiRequired).toBe(true);
    expect(result.reasoning).toMatch(/75-day/);
  });

  it('never requires NDI for banned ingredients', () => {
    const result = evaluateNDIRequirement({
      dsheaGrandfathered: false,
      ndiNotificationsCount: 0,
      grasStatus: 'NOT_GRAS',
      fdaStatus: 'BANNED',
      ingredientName: 'Ephedra',
    });
    expect(result.ndiRequired).toBe(false);
    expect(result.reasoning).toMatch(/prohibited/i);
  });
});
