"use client";

import { useState } from "react";
import { Printer, Download } from "lucide-react";

export function PrintButton({ checkId }: { checkId: string }) {
  const [downloading, setDownloading] = useState(false);

  async function downloadReport() {
    setDownloading(true);
    try {
      const res = await fetch(`/api/reports/${checkId}/pdf`);
      const data = await res.json();

      if (data.url) {
        window.open(data.url, "_blank");
      } else {
        // Fallback: re-fetch with Accept: application/json and trigger download
        const dlRes = await fetch(`/api/reports/${checkId}/pdf`);
        const blob = await dlRes.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `report-${checkId}.json`;
        a.click();
        URL.revokeObjectURL(url);
      }
    } catch {
      alert("Download failed — try printing instead.");
    } finally {
      setDownloading(false);
    }
  }

  return (
    <div className="flex gap-2">
      <button
        onClick={downloadReport}
        disabled={downloading}
        className="flex items-center gap-2 border border-gray-200 rounded-lg px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50 transition-colors"
      >
        <Download className="h-4 w-4" />
        {downloading ? "Downloading…" : "Download"}
      </button>
      <button
        onClick={() => window.print()}
        className="flex items-center gap-2 bg-brand-600 text-white rounded-lg px-3 py-1.5 text-sm font-medium hover:bg-brand-700 transition-colors"
      >
        <Printer className="h-4 w-4" />
        Print
      </button>
    </div>
  );
}
