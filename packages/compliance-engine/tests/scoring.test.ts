import { describe, it, expect } from 'vitest';
import { calculateComplianceScore, calculateCriticalScore } from '../src/scoring/score-calculator.js';
import type { CheckResult } from '../src/types.js';

describe('Score calculator', () => {
  it('returns 100 for all passing checks', () => {
    const checks: CheckResult[] = [
      { ruleId: 'A', ruleName: 'A', status: 'PASS', severity: 'LOW', message: 'ok' },
      { ruleId: 'B', ruleName: 'B', status: 'PASS', severity: 'MEDIUM', message: 'ok' },
    ];
    expect(calculateComplianceScore(checks)).toBe(100);
  });

  it('deducts 10 for a CRITICAL FAIL', () => {
    const checks: CheckResult[] = [
      { ruleId: 'A', ruleName: 'A', status: 'FAIL', severity: 'CRITICAL', message: '' },
    ];
    expect(calculateComplianceScore(checks)).toBe(90);
  });

  it('deducts 6 for a HIGH FAIL', () => {
    const checks: CheckResult[] = [
      { ruleId: 'A', ruleName: 'A', status: 'FAIL', severity: 'HIGH', message: '' },
    ];
    expect(calculateComplianceScore(checks)).toBe(94);
  });

  it('deducts half for a WARNING', () => {
    const checks: CheckResult[] = [
      { ruleId: 'A', ruleName: 'A', status: 'WARNING', severity: 'HIGH', message: '' },
    ];
    expect(calculateComplianceScore(checks)).toBe(97);
  });

  it('floors at 0 for many failures', () => {
    const checks: CheckResult[] = Array.from({ length: 15 }, (_, i) => ({
      ruleId: `R${i}`,
      ruleName: `Rule ${i}`,
      status: 'FAIL' as const,
      severity: 'CRITICAL' as const,
      message: '',
    }));
    expect(calculateComplianceScore(checks)).toBe(0);
  });

  it('skipped checks do not affect score', () => {
    const checks: CheckResult[] = [
      { ruleId: 'A', ruleName: 'A', status: 'SKIPPED', severity: 'HIGH', message: '' },
      { ruleId: 'B', ruleName: 'B', status: 'PASS', severity: 'LOW', message: '' },
    ];
    expect(calculateComplianceScore(checks)).toBe(100);
  });

  describe('calculateCriticalScore', () => {
    it('passes when no critical checks exist', () => {
      const checks: CheckResult[] = [
        { ruleId: 'A', ruleName: 'A', status: 'FAIL', severity: 'HIGH', message: '' },
      ];
      const result = calculateCriticalScore(checks);
      expect(result.criticalPass).toBe(true);
      expect(result.criticalScore).toBe(100);
      expect(result.criticalFailures).toBe(0);
    });

    it('fails when a critical check fails', () => {
      const checks: CheckResult[] = [
        { ruleId: 'A', ruleName: 'A', status: 'FAIL', severity: 'CRITICAL', message: '' },
        { ruleId: 'B', ruleName: 'B', status: 'PASS', severity: 'CRITICAL', message: '' },
      ];
      const result = calculateCriticalScore(checks);
      expect(result.criticalPass).toBe(false);
      expect(result.criticalFailures).toBe(1);
      expect(result.criticalScore).toBe(50);
    });
  });
});
