import { useState } from "react";

interface ResumeComparisonProps {
  original: string;
  optimized: string;
}

// Utility function to compute simple word-level diff
function computeWordDiff(original: string, optimized: string): { type: string; text: string }[] {
  const origWords = original.split(/(\s+)/);
  const optWords = optimized.split(/(\s+)/);
  
  const diff = [];
  let i = 0, j = 0;
  
  while (i < origWords.length || j < optWords.length) {
    if (i < origWords.length && j < optWords.length && origWords[i] === optWords[j]) {
      diff.push({ type: "same", text: origWords[i] });
      i++;
      j++;
    } else {
      // Simple heuristic: longer match means removed
      if (i < origWords.length && origWords[i].length > 2) {
        diff.push({ type: "removed", text: origWords[i] });
        i++;
      } else if (j < optWords.length) {
        diff.push({ type: "added", text: optWords[j] });
        j++;
      } else {
        i++;
      }
    }
  }
  
  return diff;
}

export function ResumeComparison({ original, optimized }: ResumeComparisonProps) {
  const [viewMode, setViewMode] = useState<"side-by-side" | "track-changes">("side-by-side");
  const wordDiff = computeWordDiff(original, optimized);
  
  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex items-center gap-3 flex-wrap">
        <span className="text-sm font-medium text-slate-400">View Mode:</span>
        <button
          onClick={() => setViewMode("side-by-side")}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
            viewMode === "side-by-side"
              ? "bg-emerald-600 text-white"
              : "bg-slate-700 text-slate-300 hover:bg-slate-600"
          }`}
        >
          Side-by-Side
        </button>
        <button
          onClick={() => setViewMode("track-changes")}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
            viewMode === "track-changes"
              ? "bg-emerald-600 text-white"
              : "bg-slate-700 text-slate-300 hover:bg-slate-600"
          }`}
        >
          Track Changes
        </button>
      </div>
      
      {viewMode === "side-by-side" ? (
        // Side-by-side view
        <div className="grid gap-4 sm:grid-cols-2">
          {/* Original Resume */}
          <div className="rounded-xl border border-slate-700 bg-slate-900/50 backdrop-blur-sm overflow-hidden">
            <div className="bg-gradient-to-r from-slate-800 to-slate-700/50 px-6 py-3 border-b border-slate-700">
              <h3 className="text-sm font-semibold text-slate-200">📄 Original Resume</h3>
            </div>
            <div className="p-6 max-h-[600px] overflow-auto">
              <pre className="whitespace-pre-wrap text-sm text-slate-300 font-mono leading-relaxed">
                {original}
              </pre>
            </div>
          </div>
          
          {/* Optimized Resume */}
          <div className="rounded-xl border border-emerald-700/50 bg-emerald-900/20 backdrop-blur-sm overflow-hidden">
            <div className="bg-gradient-to-r from-emerald-800/50 to-emerald-700/30 px-6 py-3 border-b border-emerald-700/50">
              <h3 className="text-sm font-semibold text-emerald-200">✨ Optimized Resume</h3>
            </div>
            <div className="p-6 max-h-[600px] overflow-auto">
              <pre className="whitespace-pre-wrap text-sm text-slate-300 font-mono leading-relaxed">
                {optimized}
              </pre>
            </div>
          </div>
        </div>
      ) : (
        // Track changes view
        <div className="rounded-xl border border-slate-700 bg-slate-900/50 backdrop-blur-sm overflow-hidden">
          <div className="bg-gradient-to-r from-slate-800 to-slate-700/50 px-6 py-3 border-b border-slate-700">
            <h3 className="text-sm font-semibold text-slate-200 flex items-center gap-2">
              📝 Track Changes
              <span className="text-xs font-normal text-slate-400">
                <span className="inline-block w-3 h-3 bg-red-500/30 border border-red-500 rounded mr-1"></span>
                Added
                <span className="inline-block w-3 h-3 bg-red-500/30 border border-red-500 rounded ml-3 mr-1"></span>
                Removed
              </span>
            </h3>
          </div>
          <div className="p-6 max-h-[600px] overflow-auto">
            <div className="text-sm font-mono leading-relaxed whitespace-pre-wrap">
              {wordDiff.map((item, idx) => {
                if (item.type === "same") {
                  return (
                    <span key={idx} className="text-slate-300">
                      {item.text}
                    </span>
                  );
                } else if (item.type === "added") {
                  return (
                    <span
                      key={idx}
                      className="bg-emerald-500/30 border-b-2 border-emerald-500 text-emerald-200 font-medium"
                      title="Added"
                    >
                      {item.text}
                    </span>
                  );
                } else {
                  return (
                    <span
                      key={idx}
                      className="bg-red-500/30 border-b-2 border-red-500 line-through text-red-200"
                      title="Removed"
                    >
                      {item.text}
                    </span>
                  );
                }
              })}
            </div>
          </div>
        </div>
      )}
      
      {/* Legend */}
      <div className="text-xs text-slate-400 space-y-2 px-2">
        <div className="flex items-center gap-2">
          <span className="inline-block w-4 h-4 bg-emerald-500/30 border border-emerald-500 rounded"></span>
          <span>Green: Added/Optimized text</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="inline-block w-4 h-4 bg-red-500/30 border border-red-500 rounded line-through"></span>
          <span>Red: Removed/Changed text</span>
        </div>
      </div>
    </div>
  );
}
