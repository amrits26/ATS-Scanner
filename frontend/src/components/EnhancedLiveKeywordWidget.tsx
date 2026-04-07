import { Target, Lock } from 'lucide-react';

interface EnhancedLiveKeywordWidgetProps {
  keywords?: string[];
  confidence?: number;
  isPro?: boolean;
}

export function EnhancedLiveKeywordWidget({ keywords = [], confidence = 0, isPro = false }: EnhancedLiveKeywordWidgetProps) {
  if (!keywords || keywords.length === 0) {
    return <div className="animate-pulse bg-slate-800 h-24 rounded-xl" />;
  }
  
  const displayKeywords = isPro ? keywords : keywords.slice(0, 3);
  const lockedCount = keywords.length - 3;
  
  return (
    <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
      <div className="flex items-center gap-2 mb-3">
        <Target className="w-5 h-5 text-emerald-400" />
        <h3 className="font-semibold text-white">Live Keywords</h3>
      </div>
      <div className="flex flex-wrap gap-2">
        {displayKeywords.map((kw, i) => (
          <span key={i} className="px-2 py-1 bg-slate-700 text-emerald-300 text-sm rounded">
            {kw}
          </span>
        ))}
      </div>
      {!isPro && lockedCount > 0 && (
        <div className="mt-3 text-center">
          <p className="text-yellow-300 text-sm flex items-center justify-center gap-1">
            <Lock className="w-3 h-3" /> {lockedCount} more keywords locked
          </p>
          <button className="mt-2 text-xs bg-emerald-600 hover:bg-emerald-700 px-3 py-1 rounded text-white font-semibold">
            Upgrade to Pro
          </button>
        </div>
      )}
      {confidence > 0 && (
        <p className="text-xs text-gray-400 mt-2">Confidence: {(confidence * 100).toFixed(0)}%</p>
      )}
    </div>
  );
}
