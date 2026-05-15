import { describe, it, expect } from 'vitest';
import { classifyClaim } from '../src/claims/claims-classifier.js';

describe('Claims classifier', () => {
  // Disease claims
  it('flags "cures cancer" as a disease claim', () => {
    const result = classifyClaim({ claim: 'Cures cancer and eliminates tumors' });
    expect(result.classification).toBe('DISEASE');
    expect(result.isCompliant).toBe(false);
    expect(result.riskLevel).toBe('CRITICAL');
    expect(result.checks.some((c) => c.status === 'FAIL' && c.severity === 'CRITICAL')).toBe(true);
  });

  it('flags "treats diabetes" as a disease claim', () => {
    const result = classifyClaim({ claim: 'Treats type 2 diabetes' });
    expect(result.classification).toBe('DISEASE');
    expect(result.isCompliant).toBe(false);
  });

  it('flags "prevents heart disease" as a disease claim', () => {
    const result = classifyClaim({ claim: 'Prevents heart disease' });
    expect(result.classification).toBe('DISEASE');
    expect(result.isCompliant).toBe(false);
  });

  it('flags "cures Alzheimer\'s" as a disease claim', () => {
    const result = classifyClaim({ claim: "May help cure Alzheimer's disease" });
    expect(result.classification).toBe('DISEASE');
    expect(result.isCompliant).toBe(false);
  });

  it('flags "FDA approved" language as problematic', () => {
    const result = classifyClaim({ claim: 'Our clinically proven formula is FDA approved' });
    expect(result.classification).toBe('DISEASE');
    expect(result.isCompliant).toBe(false);
  });

  // Structure/function claims (compliant)
  it('accepts "supports immune function" as structure/function', () => {
    const result = classifyClaim({ claim: 'Supports healthy immune function' });
    expect(result.classification).toBe('STRUCTURE_FUNCTION');
    expect(result.isCompliant).toBe(true);
    expect(result.riskLevel).toBe('LOW');
  });

  it('accepts "helps maintain healthy cholesterol levels" as structure/function', () => {
    const result = classifyClaim({
      claim: 'Helps maintain healthy cholesterol levels already in the normal range',
    });
    expect(result.classification).toBe('STRUCTURE_FUNCTION');
    expect(result.isCompliant).toBe(true);
  });

  it('accepts "promotes healthy joints" as structure/function', () => {
    const result = classifyClaim({ claim: 'Promotes healthy joint comfort and mobility' });
    expect(result.classification).toBe('STRUCTURE_FUNCTION');
    expect(result.isCompliant).toBe(true);
  });

  // Disclaimer requirement
  it('requires FDA disclaimer on structure/function claims without one', () => {
    const result = classifyClaim({ claim: 'Supports immune function' });
    const disclaimerCheck = result.checks.find((c) => c.ruleId === 'CLAIM-002');
    expect(disclaimerCheck?.status).toBe('FAIL');
  });

  it('passes disclaimer check when disclaimer is present', () => {
    const result = classifyClaim({
      claim: 'Supports immune function. These statements have not been evaluated by the Food and Drug Administration.',
    });
    const disclaimerCheck = result.checks.find((c) => c.ruleId === 'CLAIM-002');
    expect(disclaimerCheck?.status).toBe('PASS');
  });

  // Rewrite generation
  it('generates a safe rewrite for disease claims', () => {
    const result = classifyClaim({ claim: 'Cures arthritis' });
    expect(result.suggestedRewrite).toBeTruthy();
    expect(result.suggestedRewrite).not.toMatch(/cures/i);
  });
});
