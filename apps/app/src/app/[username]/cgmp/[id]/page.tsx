'use client';

import { useEffect, useState, useCallback } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { ArrowLeft, Save, ChevronDown, ChevronRight } from 'lucide-react';
import { ComplianceScoreBadge } from '@/components/compliance-score-badge';

interface CGMPCheckItem {
  id: string;
  question: string;
  guidance: string;
  citation: string;
  severity: string;
}

interface CGMPSection {
  id: string;
  title: string;
  description: string;
  cfr: string;
  items: CGMPCheckItem[];
}

interface SectionResult {
  sectionId: string;
  title: string;
  score: number;
  nonCompliantItems: number;
}

interface AuditData {
  id: string;
  title: string;
  overallScore: number | null;
  sections: Record<string, Record<string, boolean | null>>;
}

const SEVERITY_COLOR: Record<string, string> = {
  CRITICAL: 'text-red-600',
  HIGH: 'text-orange-600',
  MEDIUM: 'text-yellow-600',
  LOW: 'text-gray-500',
};

function SectionPanel({
  section,
  responses,
  onChange,
  result,
}: {
  section: CGMPSection;
  responses: Record<string, boolean | null>;
  onChange: (itemId: string, value: boolean | null) => void;
  result?: SectionResult;
}) {
  const [open, setOpen] = useState(false);
  const answered = section.items.filter((item) => responses[item.id] !== null && responses[item.id] !== undefined).length;

  return (
    <div className="rounded-lg border bg-white overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-3 px-5 py-4 text-left hover:bg-gray-50"
      >
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <p className="font-semibold text-gray-900">{section.title}</p>
            <span className="text-xs text-gray-400 font-mono">{section.cfr}</span>
          </div>
          <p className="text-xs text-gray-500 mt-0.5">
            {answered}/{section.items.length} answered
            {result && ` · ${result.nonCompliantItems} gap${result.nonCompliantItems !== 1 ? 's' : ''}`}
          </p>
        </div>
        {result && (
          <ComplianceScoreBadge score={result.score} size="sm" />
        )}
        {open ? <ChevronDown className="h-4 w-4 text-gray-400 flex-shrink-0" /> : <ChevronRight className="h-4 w-4 text-gray-400 flex-shrink-0" />}
      </button>

      {open && (
        <div className="border-t divide-y">
          {section.items.map((item) => {
            const val = responses[item.id] ?? null;
            return (
              <div key={item.id} className="px-5 py-4">
                <div className="flex items-start gap-4">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-gray-900 font-medium leading-snug">{item.question}</p>
                    <p className="mt-1 text-xs text-gray-500">{item.guidance}</p>
                    <p className="mt-1 text-xs font-mono text-gray-400">{item.citation}</p>
                    <span className={`mt-1 text-xs font-semibold ${SEVERITY_COLOR[item.severity] ?? 'text-gray-500'}`}>
                      {item.severity}
                    </span>
                  </div>
                  <div className="flex gap-1.5 flex-shrink-0 mt-0.5">
                    {([true, false, null] as const).map((option) => (
                      <button
                        key={String(option)}
                        onClick={() => onChange(item.id, option)}
                        className={`rounded px-2.5 py-1 text-xs font-medium border transition-colors ${
                          val === option
                            ? option === true
                              ? 'bg-green-600 text-white border-green-600'
                              : option === false
                              ? 'bg-red-600 text-white border-red-600'
                              : 'bg-gray-200 text-gray-700 border-gray-300'
                            : 'text-gray-600 border-gray-200 hover:border-gray-400'
                        }`}
                      >
                        {option === true ? 'Yes' : option === false ? 'No' : 'N/A'}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default function CGMPAuditDetailPage() {
  const params = useParams();
  const id = params.id as string;

  const [audit, setAudit] = useState<AuditData | null>(null);
  const [sections, setSections] = useState<CGMPSection[]>([]);
  const [responses, setResponses] = useState<Record<string, Record<string, boolean | null>>>({});
  const [sectionResults, setSectionResults] = useState<SectionResult[]>([]);
  const [overallScore, setOverallScore] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);

  // Load sections template
  useEffect(() => {
    fetch('/api/cgmp/sections').then((r) => r.json()).then((d) => {
      if (d.sections) setSections(d.sections);
    }).catch(() => {});
  }, []);

  // Load audit data
  useEffect(() => {
    fetch(`/api/cgmp/${id}`)
      .then((r) => r.json())
      .then((d) => {
        setAudit(d.audit);
        setResponses(d.audit?.sections ?? {});
        setOverallScore(d.audit?.overallScore ?? null);
      })
      .finally(() => setLoading(false));
  }, [id]);

  const handleChange = useCallback((sectionId: string, itemId: string, value: boolean | null) => {
    setResponses((prev) => ({
      ...prev,
      [sectionId]: { ...(prev[sectionId] ?? {}), [itemId]: value },
    }));
    setDirty(true);
  }, []);

  const handleSave = async () => {
    setSaving(true);
    try {
      const res = await fetch('/api/cgmp', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id, sections: responses }),
      });
      const data = await res.json();
      if (data.result) {
        setOverallScore(data.result.overallScore);
        setSectionResults(data.result.sections ?? []);
      }
      setDirty(false);
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <div className="text-sm text-gray-500">Loading…</div>;
  if (!audit) return <div className="text-sm text-red-500">Audit not found</div>;

  return (
    <div className="max-w-4xl">
      <Link href="/cgmp" className="mb-6 inline-flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-900">
        <ArrowLeft className="h-3.5 w-3.5" />
        Back to audits
      </Link>

      <div className="mb-6 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">{audit.title}</h1>
          <p className="mt-1 text-sm text-gray-500">21 CFR Part 111 — cGMP Readiness Assessment</p>
        </div>
        <div className="flex items-center gap-3">
          {overallScore != null && <ComplianceScoreBadge score={overallScore} />}
          <button
            onClick={handleSave}
            disabled={saving || !dirty}
            className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
          >
            <Save className="h-4 w-4" />
            {saving ? 'Saving…' : dirty ? 'Save & Score' : 'Saved'}
          </button>
        </div>
      </div>

      <div className="space-y-3">
        {sections.length === 0 ? (
          <div className="text-sm text-gray-500">Loading audit sections…</div>
        ) : (
          sections.map((section) => (
            <SectionPanel
              key={section.id}
              section={section}
              responses={responses[section.id] ?? {}}
              onChange={(itemId, value) => handleChange(section.id, itemId, value)}
              result={sectionResults.find((r) => r.sectionId === section.id)}
            />
          ))
        )}
      </div>

      {dirty && (
        <div className="mt-4 flex justify-end">
          <button
            onClick={handleSave}
            disabled={saving}
            className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-6 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
          >
            <Save className="h-4 w-4" />
            {saving ? 'Saving…' : 'Save & Score'}
          </button>
        </div>
      )}
    </div>
  );
}
