/**
 * Demo seed — creates two demo accounts with realistic formulation + compliance data.
 *
 * Demo accounts:
 *   demo@regbite.com  / Demo1234!  → Apex Nutrition, ACCOUNT_ADMIN, GROWTH plan
 *   viewer@regbite.com / Demo1234! → Apex Nutrition, VIEWER role (read-only)
 *
 * Usage:
 *   pnpm --filter @regbite/database db:demo
 *
 * Requires CLERK_SECRET_KEY env var to create actual Clerk users.
 * Without it, DB records are created with placeholder clerkUserId values
 * (manual Clerk account creation will be needed).
 */

import { PrismaClient } from '@prisma/client';

const prisma = new PrismaClient();

const DEMO_ORG_SLUG = 'apex-nutrition-demo';

const DEMO_ADMIN_EMAIL = 'demo@regbite.com';
const DEMO_VIEWER_EMAIL = 'viewer@regbite.com';
const DEMO_PASSWORD = 'Demo1234!';

// ── Compliance check result shapes ────────────────────────────────────────────

const MULTIVIT_RESULTS = {
  items: [
    { field: 'Vitamin C (Ascorbic Acid)', status: 'PASS', severity: 'LOW', message: 'GRAS substance, 500 mg well within NIH UL of 2000 mg/day', citation: '21 CFR 182.8013' },
    { field: 'Vitamin D3 (Cholecalciferol)', status: 'PASS', severity: 'LOW', message: 'GRAS substance, 2000 IU within NIH UL of 4000 IU/day', citation: '21 CFR 182.5953' },
    { field: 'Zinc (Zinc Gluconate)', status: 'PASS', severity: 'LOW', message: 'GRAS substance, 15 mg within NIH UL of 40 mg/day', citation: '21 CFR 182.8994' },
    { field: 'Magnesium (Magnesium Oxide)', status: 'WARN', severity: 'MEDIUM', message: '400 mg approaching NIH UL of 350 mg/day from supplements — consider reducing', citation: 'NIH ODS Magnesium Fact Sheet' },
    { field: 'Biotin (Vitamin B7)', status: 'PASS', severity: 'LOW', message: 'No established UL — 5000 mcg is within common industry practice', citation: '21 CFR 101.36' },
    { field: 'Supplement Facts Label Format', status: 'PASS', severity: 'LOW', message: 'All required nutrients and DV% present, format compliant with 21 CFR 101.36', citation: '21 CFR 101.36(b)' },
    { field: 'Structure/Function Claims', status: 'PASS', severity: 'LOW', message: 'All claims are structure/function claims with adequate substantiation', citation: '21 CFR 101.93' },
    { field: 'FDA Disclaimer', status: 'PASS', severity: 'LOW', message: 'Required statement "This statement has not been evaluated by the FDA" is present', citation: '21 CFR 101.93(c)' },
  ],
};

const PREWORKOUT_RESULTS = {
  items: [
    { field: 'Caffeine Anhydrous', status: 'PASS', severity: 'LOW', message: 'GRAS at 300 mg per serving; within safe consumption range', citation: '21 CFR 182.1180' },
    { field: 'Beta-Alanine', status: 'PASS', severity: 'LOW', message: 'Generally recognized as safe at 3.2 g/serving; adequate substantiation exists', citation: 'DSHEA § 6; 21 U.S.C. § 342(f)' },
    { field: 'L-Citrulline', status: 'PASS', severity: 'LOW', message: 'Permitted amino acid supplement ingredient with no known safety concerns at 6 g', citation: '21 CFR 172.320' },
    { field: 'Proprietary Blend Disclosure', status: 'FAIL', severity: 'HIGH', message: 'Individual ingredient amounts not disclosed. Under 21 CFR 101.36(b)(2), each ingredient in a proprietary blend must have its amount listed', citation: '21 CFR 101.36(b)(2)(i)' },
    { field: 'Niacin (Vitamin B3)', status: 'WARN', severity: 'MEDIUM', message: '50 mg niacin approaches the tolerable UL of 35 mg from supplements; flush-type niacin may cause adverse reactions', citation: 'NIH ODS Niacin Fact Sheet; 21 CFR 101.36' },
    { field: 'Disease Claims Risk', status: 'FAIL', severity: 'CRITICAL', message: '"Clinically proven to maximize performance" approaches a disease/drug claim under FTC substantiation standards — lacks two competent and reliable clinical studies', citation: 'FTC Policy Statement on Deceptive Acts; 15 U.S.C. § 45' },
    { field: 'Serving Size Notation', status: 'PASS', severity: 'LOW', message: 'Serving size stated in common household measure (1 scoop / 25 g)', citation: '21 CFR 101.9(b)(7)' },
  ],
};

const SLEEP_RESULTS = {
  items: [
    { field: 'Melatonin', status: 'PASS', severity: 'LOW', message: '3 mg melatonin — common supplement dose with extensive use history; not NDI-required at this dose', citation: 'DSHEA; 21 U.S.C. § 350b' },
    { field: 'Magnesium Glycinate', status: 'PASS', severity: 'LOW', message: '200 mg within NIH UL of 350 mg/day from supplements', citation: '21 CFR 182.5446' },
    { field: 'L-Theanine', status: 'PASS', severity: 'LOW', message: 'GRAS notification GRN 209 supports use in dietary supplements at 100–200 mg', citation: 'FDA GRAS Notice GRN 000209' },
    { field: 'Ashwagandha (KSM-66)', status: 'PASS', severity: 'LOW', message: 'GRAS notification GRN 786 supports use; 300 mg standardized extract within supported range', citation: 'FDA GRAS Notice GRN 000786' },
    { field: 'Supplement Facts Label Format', status: 'PASS', severity: 'LOW', message: 'All required nutrients and DV% present', citation: '21 CFR 101.36(b)' },
    { field: 'Structure/Function Claims', status: 'PASS', severity: 'LOW', message: '"Supports restful sleep" and "promotes relaxation" are acceptable structure/function claims', citation: '21 CFR 101.93(f)' },
    { field: 'FDA Disclaimer', status: 'PASS', severity: 'LOW', message: 'Required FDA disclaimer present and correctly formatted', citation: '21 CFR 101.93(c)' },
    { field: 'Allergen Statement', status: 'PASS', severity: 'LOW', message: 'No Big 9 allergens present; "Contains no allergens" statement included', citation: 'FALCPA 21 U.S.C. § 343(w)' },
  ],
};

async function createDemoClerkUsers(): Promise<{
  adminClerkId: string;
  viewerClerkId: string;
} | null> {
  const secretKey = process.env.CLERK_SECRET_KEY;
  if (!secretKey) {
    console.log('  ⚠  CLERK_SECRET_KEY not set — skipping Clerk user creation');
    console.log('     Create accounts manually in Clerk dashboard:');
    console.log(`     Email: ${DEMO_ADMIN_EMAIL}  Password: ${DEMO_PASSWORD}`);
    console.log(`     Email: ${DEMO_VIEWER_EMAIL} Password: ${DEMO_PASSWORD}`);
    return null;
  }

  const { createClerkClient } = await import('@clerk/backend');
  const clerk = createClerkClient({ secretKey });

  let adminClerkId: string;
  let viewerClerkId: string;

  // Admin user
  const existingAdmin = await clerk.users.getUserList({ emailAddress: [DEMO_ADMIN_EMAIL] });
  if (existingAdmin.data.length > 0) {
    adminClerkId = existingAdmin.data[0].id;
    console.log(`  ✓ Demo admin already exists in Clerk (${adminClerkId})`);
  } else {
    const admin = await clerk.users.createUser({
      emailAddress: [DEMO_ADMIN_EMAIL],
      password: DEMO_PASSWORD,
      firstName: 'Demo',
      lastName: 'Admin',
      skipPasswordChecks: true,
    });
    adminClerkId = admin.id;
    console.log(`  ✓ Created demo admin in Clerk (${adminClerkId})`);
  }

  // Viewer user
  const existingViewer = await clerk.users.getUserList({ emailAddress: [DEMO_VIEWER_EMAIL] });
  if (existingViewer.data.length > 0) {
    viewerClerkId = existingViewer.data[0].id;
    console.log(`  ✓ Demo viewer already exists in Clerk (${viewerClerkId})`);
  } else {
    const viewer = await clerk.users.createUser({
      emailAddress: [DEMO_VIEWER_EMAIL],
      password: DEMO_PASSWORD,
      firstName: 'Demo',
      lastName: 'Viewer',
      skipPasswordChecks: true,
    });
    viewerClerkId = viewer.id;
    console.log(`  ✓ Created demo viewer in Clerk (${viewerClerkId})`);
  }

  return { adminClerkId, viewerClerkId };
}

async function main() {
  console.log('RegBite US — demo seed\n');

  // Create Clerk users (optional)
  console.log('Creating Clerk demo users...');
  const clerkIds = await createDemoClerkUsers();

  const adminClerkId = clerkIds?.adminClerkId ?? 'demo_admin_placeholder';
  const viewerClerkId = clerkIds?.viewerClerkId ?? 'demo_viewer_placeholder';

  // ── Organization ─────────────────────────────────────────────────────────
  console.log('\nSeeding demo organization...');
  const org = await prisma.organization.upsert({
    where: { slug: DEMO_ORG_SLUG },
    update: { name: 'Apex Nutrition', plan: 'GROWTH' },
    create: {
      name: 'Apex Nutrition',
      slug: DEMO_ORG_SLUG,
      plan: 'GROWTH',
    },
  });
  console.log(`  ✓ Org: ${org.name} (${org.id})`);

  // ── Members ───────────────────────────────────────────────────────────────
  console.log('\nSeeding demo members...');
  const adminMember = await prisma.member.upsert({
    where: { clerkUserId: adminClerkId },
    update: { email: DEMO_ADMIN_EMAIL, name: 'Demo Admin', role: 'ACCOUNT_ADMIN', organizationId: org.id },
    create: {
      clerkUserId: adminClerkId,
      email: DEMO_ADMIN_EMAIL,
      name: 'Demo Admin',
      role: 'ACCOUNT_ADMIN',
      organizationId: org.id,
    },
  });
  console.log(`  ✓ Admin: ${adminMember.email}`);

  const viewerMember = await prisma.member.upsert({
    where: { clerkUserId: viewerClerkId },
    update: { email: DEMO_VIEWER_EMAIL, name: 'Demo Viewer', role: 'VIEWER', organizationId: org.id },
    create: {
      clerkUserId: viewerClerkId,
      email: DEMO_VIEWER_EMAIL,
      name: 'Demo Viewer',
      role: 'VIEWER',
      organizationId: org.id,
    },
  });
  console.log(`  ✓ Viewer: ${viewerMember.email}`);

  // ── Subscription ──────────────────────────────────────────────────────────
  console.log('\nSeeding demo subscription...');
  const existing = await prisma.subscription.findFirst({ where: { organizationId: org.id } });
  if (!existing) {
    await prisma.subscription.create({
      data: {
        organizationId: org.id,
        stripeSubscriptionId: 'demo_sub_placeholder',
        plan: 'GROWTH',
        status: 'ACTIVE',
        currentPeriodEnd: new Date(Date.now() + 30 * 24 * 60 * 60 * 1000),
      },
    });
    console.log('  ✓ GROWTH subscription (ACTIVE)');
  } else {
    console.log('  ✓ Subscription already exists');
  }

  // ── Formulations + Checks ─────────────────────────────────────────────────
  console.log('\nSeeding demo formulations...');

  const formulations = [
    {
      productName: 'Apex MultiVit PRO',
      productType: 'VITAMIN_MINERAL' as const,
      servingSize: '2 capsules',
      servingsPerContainer: '60',
      claims: [
        'Supports immune system function',
        'Promotes cellular energy production',
        'This statement has not been evaluated by the Food and Drug Administration. This product is not intended to diagnose, treat, cure, or prevent any disease.',
      ],
      ingredients: [
        { name: 'Vitamin C (Ascorbic Acid)', amount: 500, unit: 'mg', casNumber: '50-81-7' },
        { name: 'Vitamin D3 (Cholecalciferol)', amount: 2000, unit: 'IU', casNumber: '67-97-0' },
        { name: 'Zinc (Zinc Gluconate)', amount: 15, unit: 'mg', casNumber: '4468-02-4' },
        { name: 'Magnesium (Magnesium Oxide)', amount: 400, unit: 'mg', casNumber: '1309-48-4' },
        { name: 'Biotin (Vitamin B7)', amount: 5000, unit: 'mcg', casNumber: '58-85-5' },
        { name: 'Folate (as Methylfolate)', amount: 400, unit: 'mcg DFE', casNumber: '59-30-3' },
      ],
      complianceScore: 87,
      status: 'APPROVED' as const,
      checkType: 'FULL' as const,
      checkScore: 87,
      checkResults: MULTIVIT_RESULTS,
    },
    {
      productName: 'Pre-Workout X',
      productType: 'SPORTS_NUTRITION' as const,
      servingSize: '1 scoop (25g)',
      servingsPerContainer: '30',
      claims: [
        'Clinically proven to maximize performance',
        'Supports muscle endurance and strength',
        'This statement has not been evaluated by the Food and Drug Administration.',
      ],
      ingredients: [
        { name: 'Caffeine Anhydrous', amount: 300, unit: 'mg', casNumber: '58-08-2' },
        { name: 'Beta-Alanine', amount: 3200, unit: 'mg', casNumber: '107-95-9' },
        { name: 'L-Citrulline', amount: 6000, unit: 'mg', casNumber: '372-75-8' },
        { name: 'Niacin (Vitamin B3)', amount: 50, unit: 'mg', casNumber: '59-67-6' },
        { name: 'Vitamin B12 (Methylcobalamin)', amount: 500, unit: 'mcg', casNumber: '68-19-9' },
      ],
      complianceScore: 62,
      status: 'UNDER_REVIEW' as const,
      checkType: 'FULL' as const,
      checkScore: 62,
      checkResults: PREWORKOUT_RESULTS,
    },
    {
      productName: 'Sleep & Recovery Formula',
      productType: 'DIETARY_SUPPLEMENT' as const,
      servingSize: '2 capsules',
      servingsPerContainer: '30',
      claims: [
        'Supports restful sleep',
        'Promotes relaxation and recovery',
        'This statement has not been evaluated by the Food and Drug Administration. This product is not intended to diagnose, treat, cure, or prevent any disease.',
      ],
      ingredients: [
        { name: 'Melatonin', amount: 3, unit: 'mg', casNumber: '73-31-4' },
        { name: 'Magnesium (Magnesium Glycinate)', amount: 200, unit: 'mg', casNumber: '14783-68-7' },
        { name: 'L-Theanine', amount: 200, unit: 'mg', casNumber: '3081-61-6' },
        { name: 'Ashwagandha Extract (KSM-66)', amount: 300, unit: 'mg', casNumber: '90147-36-7' },
        { name: 'Valerian Root Extract', amount: 150, unit: 'mg', casNumber: '8057-49-6' },
      ],
      complianceScore: 91,
      status: 'APPROVED' as const,
      checkType: 'FULL' as const,
      checkScore: 91,
      checkResults: SLEEP_RESULTS,
    },
  ];

  for (const f of formulations) {
    const existing = await prisma.formulation.findFirst({
      where: { organizationId: org.id, productName: f.productName },
    });

    let formulation;
    if (existing) {
      formulation = existing;
      console.log(`  ✓ ${f.productName} (already exists)`);
    } else {
      formulation = await prisma.formulation.create({
        data: {
          organizationId: org.id,
          productName: f.productName,
          productType: f.productType,
          servingSize: f.servingSize,
          servingsPerContainer: f.servingsPerContainer,
          ingredients: f.ingredients,
          claims: f.claims,
          complianceScore: f.complianceScore,
          status: f.status,
        },
      });
      console.log(`  ✓ ${f.productName} — score ${f.complianceScore}`);
    }

    // Compliance check
    const existingCheck = await prisma.complianceCheck.findFirst({
      where: { formulationId: formulation.id, checkType: f.checkType },
    });

    if (!existingCheck) {
      await prisma.complianceCheck.create({
        data: {
          formulationId: formulation.id,
          organizationId: org.id,
          checkType: f.checkType,
          status: 'COMPLETED',
          overallScore: f.checkScore,
          results: f.checkResults,
          regulatoryCitations: {
            primary: ['21 CFR Part 101', 'DSHEA 1994', '21 CFR Part 111'],
            secondary: ['FTC Act Section 5', 'NIH ODS Fact Sheets'],
          },
        },
      });
    }
  }

  // ── Activity logs ─────────────────────────────────────────────────────────
  console.log('\nSeeding demo activity logs...');
  const logCount = await prisma.activityLog.count({ where: { organizationId: org.id } });
  if (logCount === 0) {
    const logs = [
      { action: 'FORMULATION_CREATED', detail: 'Created "Apex MultiVit PRO"', resourceType: 'Formulation', daysAgo: 14 },
      { action: 'COMPLIANCE_CHECK_RUN', detail: 'Full compliance check — MultiVit PRO (score: 87)', resourceType: 'ComplianceCheck', daysAgo: 13 },
      { action: 'FORMULATION_CREATED', detail: 'Created "Pre-Workout X"', resourceType: 'Formulation', daysAgo: 7 },
      { action: 'COMPLIANCE_CHECK_RUN', detail: 'Full compliance check — Pre-Workout X (score: 62)', resourceType: 'ComplianceCheck', daysAgo: 6 },
      { action: 'FORMULATION_CREATED', detail: 'Created "Sleep & Recovery Formula"', resourceType: 'Formulation', daysAgo: 3 },
      { action: 'COMPLIANCE_CHECK_RUN', detail: 'Full compliance check — Sleep Formula (score: 91)', resourceType: 'ComplianceCheck', daysAgo: 2 },
      { action: 'MEMBER_INVITED', detail: 'Invited viewer@regbite.com as VIEWER', resourceType: 'Member', daysAgo: 10 },
    ];

    for (const log of logs) {
      const { daysAgo, ...data } = log;
      await prisma.activityLog.create({
        data: {
          ...data,
          memberId: adminMember.id,
          organizationId: org.id,
          createdAt: new Date(Date.now() - daysAgo * 24 * 60 * 60 * 1000),
        },
      });
    }
    console.log(`  ✓ ${logs.length} activity log entries`);
  } else {
    console.log('  ✓ Activity logs already exist');
  }

  console.log('\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
  console.log('Demo seed complete!\n');
  console.log('Demo accounts:');
  console.log(`  Admin   ${DEMO_ADMIN_EMAIL} / ${DEMO_PASSWORD}  (ACCOUNT_ADMIN)`);
  console.log(`  Viewer  ${DEMO_VIEWER_EMAIL} / ${DEMO_PASSWORD} (VIEWER, read-only)`);
  if (!clerkIds) {
    console.log('\n⚠  Clerk users NOT created (no CLERK_SECRET_KEY).');
    console.log('   Re-run after setting CLERK_SECRET_KEY, or create the accounts manually.');
    console.log('   After creating Clerk users, run this seed again to link their IDs.');
  }
  console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n');
}

main()
  .catch((e) => {
    console.error('Demo seed failed:', e);
    process.exit(1);
  })
  .finally(() => prisma.$disconnect());
