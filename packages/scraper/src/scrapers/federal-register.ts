/**
 * Federal Register API scraper — dietary supplement regulations
 *
 * Source: https://www.federalregister.gov/api/v1/documents
 *
 * The Federal Register publishes all FDA rulemaking, proposed rules, and
 * guidance documents. This scraper queries the JSON API for supplement-related
 * notices and stores them as RegulatoryChange entries.
 */

import { prisma } from '@regbite/database';
import { fetchJson } from '../lib/parser.js';
import { hashDocument } from '../lib/hasher.js';
import type { FDAScraperResult } from '../types.js';

const FR_API = 'https://www.federalregister.gov/api/v1/documents.json';

// Search terms covering DSHEA, dietary supplements, 21 CFR Part 111 cGMP, etc.
const SEARCH_QUERIES = [
  'dietary supplements DSHEA',
  'dietary supplement 21 CFR 111',
  'new dietary ingredient notification',
  'structure function claims dietary supplement',
];

const FIVE_YEARS_AGO = new Date(Date.now() - 5 * 365 * 24 * 60 * 60 * 1000)
  .toISOString()
  .split('T')[0];

interface FRDocument {
  document_number: string;
  title: string;
  abstract: string | null;
  type: string;
  action: string | null;
  publication_date: string;
  html_url: string;
  agencies: { name: string }[];
}

interface FRApiResponse {
  results: FRDocument[];
  count: number;
  total_pages: number;
}

function classifyChangeType(doc: FRDocument): string {
  const text = `${doc.title} ${doc.abstract ?? ''} ${doc.action ?? ''}`.toLowerCase();
  if (text.includes('final rule') || text.includes('amend')) return 'AMENDMENT';
  if (text.includes('proposed rule') || text.includes('advance notice')) return 'NEW_REGULATION';
  if (text.includes('guidance') || text.includes('draft guidance')) return 'GUIDANCE';
  if (text.includes('warning') || text.includes('enforcement')) return 'WARNING';
  if (text.includes('cgmp') || text.includes('manufacturing practice')) return 'CGMP_UPDATE';
  if (text.includes('new dietary ingredient') || text.includes('ndi')) return 'NDI_DECISION';
  if (text.includes('label') || text.includes('supplement facts')) return 'LABEL_REQUIREMENT';
  if (text.includes('claim') || text.includes('ftc')) return 'CLAIMS_ENFORCEMENT';
  return 'GUIDANCE';
}

function classifySeverity(doc: FRDocument): string {
  const text = `${doc.title} ${doc.action ?? ''}`.toLowerCase();
  if (text.includes('final rule') || text.includes('direct final')) return 'HIGH';
  if (text.includes('proposed rule')) return 'MEDIUM';
  return 'LOW';
}

function affectedModules(doc: FRDocument): string[] {
  const text = `${doc.title} ${doc.abstract ?? ''}`.toLowerCase();
  const modules: string[] = [];
  if (text.includes('ingredient') || text.includes('ndi')) modules.push('INGREDIENT');
  if (text.includes('cgmp') || text.includes('manufactur')) modules.push('CGMP');
  if (text.includes('label') || text.includes('supplement facts')) modules.push('LABEL');
  if (text.includes('claim')) modules.push('CLAIMS');
  return modules.length ? modules : ['INGREDIENT'];
}

async function queryFederalRegister(query: string): Promise<FRDocument[]> {
  const params = new URLSearchParams();
  params.set('conditions[term]', query);
  params.set('conditions[agencies][]', 'food-and-drug-administration');
  params.set('conditions[publication_date][gte]', FIVE_YEARS_AGO);
  params.append('conditions[type][]', 'RULE');
  params.append('conditions[type][]', 'PRORULE');
  params.append('conditions[type][]', 'NOTICE');
  params.set('per_page', '40');
  params.set('order', 'newest');
  params.set(
    'fields[]',
    ['document_number', 'title', 'abstract', 'type', 'action', 'publication_date', 'html_url', 'agencies'].join(','),
  );

  const url = `${FR_API}?${params.toString()}`;
  const data = await fetchJson<FRApiResponse>(url);
  return data.results ?? [];
}

export async function scrapeFederalRegister(): Promise<FDAScraperResult> {
  const result: FDAScraperResult = {
    source: 'FDA_FEDERAL_REGISTER',
    url: FR_API,
    scrapedAt: new Date(),
    records: [],
    errors: [],
  };

  const seen = new Set<string>();

  for (const query of SEARCH_QUERIES) {
    try {
      const docs = await queryFederalRegister(query);
      console.log(`[FR] Query "${query}": ${docs.length} documents`);

      for (const doc of docs) {
        if (seen.has(doc.document_number)) continue;
        seen.add(doc.document_number);

        try {
          const docHash = hashDocument(`fr:${doc.document_number}`);
          const exists = await prisma.regulatoryChange.findUnique({ where: { documentHash: docHash } });
          if (exists) continue;

          await prisma.regulatoryChange.create({
            data: {
              source: 'FDA_FEDERAL_REGISTER',
              sourceUrl: doc.html_url,
              documentTitle: doc.title,
              summary: doc.abstract?.slice(0, 1000) ?? null,
              changeType: classifyChangeType(doc) as never,
              severity: classifySeverity(doc) as never,
              affectedModules: affectedModules(doc),
              documentHash: docHash,
              publishedAt: new Date(doc.publication_date),
            },
          });

          result.records.push({ documentNumber: doc.document_number, title: doc.title });
        } catch (err) {
          result.errors.push(`Doc ${doc.document_number}: ${(err as Error).message}`);
        }
      }
    } catch (err) {
      result.errors.push(`Query "${query}" failed: ${(err as Error).message}`);
    }
  }

  return result;
}

if (process.argv[1]?.includes('federal-register')) {
  scrapeFederalRegister()
    .then((r) =>
      console.log(`[FR] Done — ${r.records.length} records, ${r.errors.length} errors`),
    )
    .catch(console.error)
    .finally(() => prisma.$disconnect());
}
