export const PLANS = {
  starter: {
    name: "Starter",
    priceMonthly: 19900,
    formulations: 10,
    users: 2,
    modules: ["ingredient", "formula", "label", "claims"],
  },
  growth: {
    name: "Growth",
    priceMonthly: 39900,
    formulations: 50,
    users: 5,
    modules: [
      "ingredient",
      "formula",
      "label",
      "claims",
      "ndi",
      "cgmp",
      "regulatory",
    ],
  },
  professional: {
    name: "Professional",
    priceMonthly: 69900,
    formulations: 200,
    users: 15,
    modules: ["all"],
  },
  enterprise: {
    name: "Enterprise",
    priceMonthly: 99900,
    formulations: null,
    users: null,
    modules: ["all"],
  },
  consultant: {
    name: "Consultant",
    priceMonthly: 49900,
    formulations: 100,
    users: 3,
    modules: ["all"],
    multiOrg: true,
  },
} as const;

export type PlanKey = keyof typeof PLANS;

export const SEVERITY_DEDUCTIONS = {
  CRITICAL: 10,
  HIGH: 6,
  MEDIUM: 3,
  LOW: 1,
} as const;

export const PRODUCT_TYPES = [
  "DIETARY_SUPPLEMENT",
  "VITAMIN_MINERAL",
  "HERBAL_BOTANICAL",
  "AMINO_ACID",
  "SPORTS_NUTRITION",
  "PROBIOTICS",
  "SPECIALTY",
] as const;

export const USER_ROLES = [
  "SUPER_ADMIN",
  "ACCOUNT_ADMIN",
  "EDITOR",
  "VIEWER",
  "CONSULTANT",
] as const;
