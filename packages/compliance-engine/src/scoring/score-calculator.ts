import { SEVERITY_DEDUCTIONS } from "@regbite/config";
import type { CheckResult } from "../types";

export function calculateComplianceScore(checks: CheckResult[]): number {
  if (checks.length === 0) return 0;

  let deductions = 0;
  for (const check of checks) {
    const penalty = SEVERITY_DEDUCTIONS[check.severity] ?? 1;
    if (check.status === "FAIL") {
      deductions += penalty;
    } else if (check.status === "WARNING") {
      deductions += penalty * 0.5;
    }
  }

  return Math.max(0, Math.round(100 - deductions));
}

export function calculateCriticalScore(checks: CheckResult[]): {
  criticalPass: boolean;
  criticalScore: number;
  criticalFailures: number;
} {
  const criticalChecks = checks.filter((c) => c.severity === "CRITICAL");
  if (criticalChecks.length === 0) {
    return { criticalPass: true, criticalScore: 100, criticalFailures: 0 };
  }

  const failures = criticalChecks.filter((c) => c.status === "FAIL").length;
  const score = Math.round(
    ((criticalChecks.length - failures) / criticalChecks.length) * 100
  );

  return {
    criticalPass: failures === 0,
    criticalScore: score,
    criticalFailures: failures,
  };
}
