import React, { useState, useEffect } from 'react';

interface KeywordValue {
  keyword: string;
  impact_percent: number;
  confidence: number;
}

interface EnhancedLiveKeywordData {
  keywords_found: number;
  keywords_added: number;
  top_added: string[];
  predicted_boost: number;
  status_message: string;
  free_tier_preview: string[];
  locked_keywords_count: number;
  before_score: number;
  after_score_predicted: number;
  match_percentage: number;
  competitor_avg_score: number;
  current_step: number;
  step_action: string;
  time_elapsed_seconds: number;
  ai_confidence: number;
  keyword_values: KeywordValue[];
  steps_log: string[];
}

interface EnhancedLiveKeywordWidgetProps {
  data: EnhancedLiveKeywordData;
  isFreeUser: boolean;
}

export function EnhancedLiveKeywordWidget({ data, isFreeUser }: EnhancedLiveKeywordWidgetProps) {
  const [visibleKeywords, setVisibleKeywords] = useState<number>(0);

  // Stagger keyword animations (pop in one-by-one)
  useEffect(() => {
    if (data.free_tier_preview.length === 0) return;
    if (visibleKeywords >= data.free_tier_preview.length) return;

    const timer = setTimeout(() => {
      setVisibleKeywords(prev => prev + 1);
    }, 200);

    return () => clearTimeout(timer);
  }, [visibleKeywords, data.free_tier_preview.length]);

  if (!data || data.keywords_added === 0) return null;

  const scoreGain = Math.round(data.after_score_predicted - data.before_score);
  const competitorBeatsBy = Math.round(data.after_score_predicted - data.competitor_avg_score);
  const timeRemaining = Math.max(0, 45 - data.time_elapsed_seconds);

  return (
    <div className="space-y-4 mb-4">
      <style>{`
        @keyframes fadeInScale {
          from {
            opacity: 0;
            transform: scale(0.8);
          }
          to {
            opacity: 1;
            transform: scale(1);
          }
        }
        .keyword-pop {
          animation: fadeInScale 0.3s ease-out backwards;
        }
      `}</style>

      {/* === HEADER: AI War Room Badge === */}
      <div className="flex items-center justify-between bg-gradient-to-r from-purple-900/60 to-blue-900/60 border border-purple-500 rounded-lg p-3">
        <div className="flex items-center gap-2">
          <span className="text-2xl animate-pulse">🤖</span>
          <span className="text-xs font-bold text-purple-300 tracking-widest">AI WAR ROOM</span>
        </div>
        <div className="text-xs text-purple-300 font-semibold">
          {timeRemaining}s remaining
        </div>
      </div>

      {/* === SCORE TRANSFORMATION CARD === */}
      <div className="bg-slate-900 border border-slate-700 rounded-lg p-4 space-y-3">
        <p className="text-xs text-slate-400 font-semibold">REAL-TIME SCORE TRANSFORMATION</p>
        
        <div className="grid grid-cols-3 gap-2">
          {/* Before Score */}
          <div className="text-center">
            <p className="text-3xl font-black text-slate-400">{Math.round(data.before_score)}</p>
            <p className="text-xs text-slate-500">Before</p>
          </div>

          {/* Arrow */}
          <div className="flex items-center justify-center">
            <span className="text-2xl animate-bounce">→</span>
          </div>

          {/* After Score */}
          <div className="text-center">
            <p className="text-3xl font-black text-green-400">{Math.round(data.after_score_predicted)}</p>
            <p className="text-xs text-green-400">Predicted</p>
          </div>
        </div>

        {/* Progress bar animation */}
        <div className="relative h-2 bg-slate-800 rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-green-500 to-emerald-400 rounded-full transition-all duration-1000"
            style={{ width: `${Math.min(100, (data.after_score_predicted / 100) * 100)}%` }}
          />
        </div>

        {/* Gain badge */}
        <div className="text-center">
          <span className="inline-block bg-green-900/50 border border-green-600 px-3 py-1 rounded text-green-300 text-sm font-bold">
            +{scoreGain} points 🚀
          </span>
        </div>
      </div>

      {/* === AI ACTION FEED === */}
      <div className="bg-slate-900 border border-slate-700 rounded-lg p-3 space-y-2">
        <p className="text-xs text-slate-400 font-semibold">AI ANALYSIS PIPELINE</p>
        
        {/* Recent steps */}
        <div className="space-y-1 max-h-20 overflow-y-auto text-xs text-slate-300">
          {data.steps_log.slice(-3).map((step, i) => (
            <div key={i} className="flex items-center gap-2">
              <span className="text-slate-600">→</span>
              <span>{step}</span>
            </div>
          ))}
        </div>

        {/* Current step with confidence */}
        {data.step_action && (
          <div className="bg-purple-900/30 border border-purple-700 rounded px-2 py-1 mt-2">
            <p className="text-purple-300 font-semibold text-xs flex items-center gap-2">
              <span className="animate-pulse">⚙️</span>
              {data.step_action}
              <span className="ml-auto text-purple-400">{Math.round(data.ai_confidence)}% confidence</span>
            </p>
          </div>
        )}
      </div>

      {/* === KEYWORDS CARD WITH STAGGER ANIMATION === */}
      <div className="bg-slate-900 border border-slate-700 rounded-lg p-4 space-y-3">
        <div className="flex items-center justify-between">
          <p className="text-xs text-slate-400 font-semibold">KEYWORDS INJECTED ({data.keywords_added})</p>
          <span className="text-xs bg-amber-900/50 text-amber-300 px-2 py-1 rounded font-semibold">
            {Math.round(data.match_percentage)}% match
          </span>
        </div>

        {/* Keywords grid with stagger animation */}
        <div className="flex flex-wrap gap-2">
          {data.free_tier_preview.slice(0, visibleKeywords).map((keyword, i) => (
            <div
              key={i}
              className="keyword-pop"
              style={{
                animationDelay: `${i * 0.1}s`,
              }}
            >
              <span className="inline-block bg-emerald-700 px-3 py-1 rounded-full text-xs font-semibold text-emerald-100 border border-emerald-600 shadow-lg">
                ✨ {keyword}
              </span>
            </div>
          ))}
        </div>

        {/* Teaser for free users */}
        {isFreeUser && data.locked_keywords_count > 0 && (
          <div className="mt-3 bg-gradient-to-r from-amber-900/50 to-orange-900/50 border-2 border-amber-600 rounded-lg p-3 text-center">
            <p className="text-amber-300 text-sm font-bold mb-2">
              +{data.locked_keywords_count} MORE KEYWORDS WAITING
            </p>
            <p className="text-xs text-amber-200 mb-3">
              PRO users see all {data.keywords_added} keywords + get personalized keyword recommendations
            </p>
            <button className="w-full bg-gradient-to-r from-amber-600 to-orange-600 hover:from-amber-500 hover:to-orange-500 text-white font-bold py-2 px-4 rounded-lg transition-all duration-200 transform hover:scale-105">
              🔓 UNLOCK PRO ({data.locked_keywords_count} WAITING)
            </button>
          </div>
        )}
      </div>

      {/* === COMPETITOR BENCHMARK === */}
      <div className="bg-blue-950/40 border border-blue-700 rounded-lg p-3 text-center">
        <p className="text-blue-300 text-xs font-bold mb-1">YOUR EDGE</p>
        <p className="text-blue-200 text-sm">
          You'll beat {Math.round(data.competitor_avg_score)} avg competitors
          <span className="block text-green-400 font-bold text-lg">+{competitorBeatsBy} points ahead</span>
        </p>
      </div>

      {/* === CONVERSION MESSAGE === */}
      <div className="bg-green-950/40 border border-green-700 rounded-lg p-3 text-center">
        <p className="text-green-300 text-xs font-bold">IF YOU LAND 1 INTERVIEW</p>
        <p className="text-green-200 text-xs">PRO membership pays for itself 100x over</p>
      </div>
    </div>
  );
}
