/**
 * NDI (New Dietary Ingredient) requirement evaluator
 *
 * Under DSHEA § 8 (21 U.S.C. § 350b), a dietary supplement containing an NDI
 * (ingredient not marketed in the US before October 15, 1994) requires a 75-day
 * pre-market notification to the FDA unless the ingredient meets one of the
 * exemptions.
 *
 * Reference: FDA Draft Guidance on NDI Notifications (2016, updated 2022)
 */

export interface NDIEvaluationResult {
  ndiRequired: boolean;
  reasoning: string;
  exemption?: string;
}

export function evaluateNDIRequirement(params: {
  dsheaGrandfathered: boolean;
  ndiNotificationsCount: number;
  grasStatus: string;
  fdaStatus: string;
  ingredientName: string;
}): NDIEvaluationResult {
  const { dsheaGrandfathered, ndiNotificationsCount, grasStatus, fdaStatus, ingredientName } = params;

  // BANNED ingredients don't qualify for NDI — they're prohibited outright
  if (fdaStatus === 'BANNED') {
    return {
      ndiRequired: false,
      reasoning: `${ingredientName} is prohibited under FDA regulations and cannot be marketed as a dietary supplement regardless of NDI status.`,
    };
  }

  // Grandfathered (marketed before Oct 15, 1994) — no NDI notification needed
  if (dsheaGrandfathered) {
    return {
      ndiRequired: false,
      reasoning: `${ingredientName} was marketed as a dietary supplement before October 15, 1994 (DSHEA cutoff) and is not subject to the NDI notification requirement.`,
      exemption: 'Pre-DSHEA ingredient (21 U.S.C. § 350b(a))',
    };
  }

  // FDA-affirmed GRAS — generally exempt from NDI notification
  if (grasStatus === 'FDA_AFFIRMED' || grasStatus === 'SELF_AFFIRMED') {
    return {
      ndiRequired: false,
      reasoning: `${ingredientName} has GRAS (Generally Recognized as Safe) status. While GRAS and NDI are separate pathways, GRAS status indicates safety has been established and NDI notification may not be required.`,
      exemption: 'GRAS status (21 U.S.C. § 321(s))',
    };
  }

  // Existing NDI notifications on record — notification already submitted
  if (ndiNotificationsCount > 0) {
    return {
      ndiRequired: false,
      reasoning: `${ingredientName} has ${ndiNotificationsCount} existing NDI notification(s) on file with the FDA. A new notification is generally not required unless the intended conditions of use differ materially from what was previously notified.`,
      exemption: 'Existing NDI notification on file',
    };
  }

  // Default: NDI notification required
  return {
    ndiRequired: true,
    reasoning: `${ingredientName} does not appear to have been marketed as a dietary supplement before October 15, 1994, and lacks existing NDI notifications or GRAS status. A 75-day pre-market NDI notification to the FDA is required under DSHEA § 8 (21 U.S.C. § 350b) before marketing.`,
  };
}
