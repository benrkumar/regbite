import { PrismaClient } from '@prisma/client';
import { readFileSync } from 'fs';
import { join } from 'path';

const prisma = new PrismaClient();

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function loadJson(filename: string): any[] {
  return JSON.parse(readFileSync(join(__dirname, filename), 'utf-8'));
}

async function seedDailyValues() {
  const data = loadJson('daily-values-seed.json');
  console.log(`Seeding ${data.length} FDA daily values...`);
  for (const dv of data) {
    await prisma.fDADailyValue.upsert({
      where: { nutrient: dv.nutrient },
      update: {
        unit: dv.unit,
        dvAdult: dv.dvAdult,
        dvChild: dv.dvChild ?? null,
        dvPregnant: dv.dvPregnant ?? null,
        dvLactating: dv.dvLactating ?? null,
        source: dv.source,
      },
      create: {
        nutrient: dv.nutrient,
        unit: dv.unit,
        dvAdult: dv.dvAdult,
        dvChild: dv.dvChild ?? null,
        dvPregnant: dv.dvPregnant ?? null,
        dvLactating: dv.dvLactating ?? null,
        source: dv.source,
      },
    });
  }
  console.log(`  ✓ ${data.length} daily values`);
}

async function seedIngredients() {
  const data = loadJson('us-ingredients-seed.json');
  console.log(`Seeding ${data.length} ingredients...`);
  for (const ing of data) {
    await prisma.uSIngredient.upsert({
      where: { name: ing.name },
      update: {
        aliases: ing.aliases ?? [],
        casNumber: ing.casNumber ?? null,
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        fdaStatus: ing.fdaStatus as any,
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        grasStatus: ing.grasStatus as any,
        dsheaGrandfathered: ing.dsheaGrandfathered ?? false,
        ndiNotificationsCount: ing.ndiNotificationsCount ?? 0,
        prop65Listed: ing.prop65Listed ?? false,
        upperIntakeLevel: ing.upperIntakeLevel ?? null,
        safeUsageLevel: ing.safeUsageLevel ?? null,
        advisoryNotes: ing.advisoryNotes ?? null,
        regulatoryCitations: ing.regulatoryCitations ?? [],
        lastReviewedAt: new Date(),
      },
      create: {
        name: ing.name,
        aliases: ing.aliases ?? [],
        casNumber: ing.casNumber ?? null,
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        fdaStatus: ing.fdaStatus as any,
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        grasStatus: ing.grasStatus as any,
        dsheaGrandfathered: ing.dsheaGrandfathered ?? false,
        ndiNotificationsCount: ing.ndiNotificationsCount ?? 0,
        prop65Listed: ing.prop65Listed ?? false,
        upperIntakeLevel: ing.upperIntakeLevel ?? null,
        safeUsageLevel: ing.safeUsageLevel ?? null,
        advisoryNotes: ing.advisoryNotes ?? null,
        regulatoryCitations: ing.regulatoryCitations ?? [],
        lastReviewedAt: new Date(),
      },
    });
  }
  console.log(`  ✓ ${data.length} ingredients`);
}

async function seedProp65Chemicals() {
  const data = loadJson('prop65-chemicals-seed.json');
  console.log(`Seeding ${data.length} Prop 65 chemicals...`);
  for (const chem of data) {
    await prisma.prop65Chemical.upsert({
      where: { chemical: chem.chemical },
      update: {
        casNumber: chem.casNumber ?? null,
        listingMechanism: chem.listingMechanism ?? null,
        dateAdded: chem.dateAdded ? new Date(chem.dateAdded) : null,
        relevance: chem.relevance ?? null,
      },
      create: {
        chemical: chem.chemical,
        casNumber: chem.casNumber ?? null,
        listingMechanism: chem.listingMechanism ?? null,
        dateAdded: chem.dateAdded ? new Date(chem.dateAdded) : null,
        relevance: chem.relevance ?? null,
      },
    });
  }
  console.log(`  ✓ ${data.length} Prop 65 chemicals`);
}

async function main() {
  console.log('RegBite US — database seed\n');
  await seedDailyValues();
  await seedIngredients();
  await seedProp65Chemicals();
  console.log('\nSeed complete.');
}

main()
  .catch((e) => {
    console.error('Seed failed:', e);
    process.exit(1);
  })
  .finally(() => prisma.$disconnect());
