import React, { useState } from 'react';
import { ChevronDown, ChevronUp, HelpCircle } from 'lucide-react';
import type { ATSScoreResponse } from '../types';

interface CredibilityCardProps {
  atsScoreData: ATSScoreResponse;
}

/**
 * Phase 6: Credibility Card
 * 
 * Displays:
 * 1. Percentile ranking ("You scored higher than X% of users")
 * 2. Confidence score ("92% confident in this assessment")
 * 3. Algorithm breakdown (expandable) showing weighting of scoring factors
 * 4. Keyword impact predictions
 */
export const CredibilityCard: React.FC<CredibilityCardProps> = ({ atsScoreData }) => {
  const [expandAlgorithm, setExpandAlgorithm] = useState(false);
  const [expandKeywords, setExpandKeywords] = useState(false);

  const percentile = atsScoreData.percentile_rank ?? 50;
  const confidence = atsScoreData.confidence_score ?? 75;
  const breakdown = atsScoreData.algorithm_breakdown || {
    keywords: 40,
    format: 30,
    experience: 20,
    structure: 10,
  };
  const keywordImpact = atsScoreData.keyword_impact_data || [];

  // Interpret percentile ranking
  let percentileLabel = '';
  if (percentile >= 80) {
    percentileLabel = 'Top Performer';
  } else if (percentile >= 60) {
    percentileLabel = 'Above Average';
  } else if (percentile >= 40) {
    percentileLabel = 'Average';
  } else {
    percentileLabel = 'Below Average';
  }

  // Color based on score
  const percentileColor =
    percentile >= 80
      ? 'from-emerald-500 to-teal-500'
      : percentile >= 60
      ? 'from-blue-500 to-cyan-500'
      : percentile >= 40
      ? 'from-yellow-500 to-amber-500'
      : 'from-red-500 to-orange-500';

  return (
    <div className="bg-gradient-to-br from-slate-700 to-slate-800 rounded-lg p-6 border border-slate-600 space-y-6">
      {/* Header */}
      <div>
        <h3 className="text-lg font-semibold text-white mb-1 flex items-center gap-2">
          <span>📊 Assessment Credibility</span>
          <HelpCircle className="w-4 h-4 text-slate-400" />
        </h3>
        <p className="text-sm text-slate-300">
          How we're confident in your score and what drives it
        </p>
      </div>

      {/* Percentile Ranking */}
      <div>
        <div className="flex justify-between items-start mb-3">
          <div>
            <p className="text-sm font-medium text-slate-300 mb-1">Your Ranking</p>
            <h4 className={`text-3xl font-bold bg-gradient-to-r ${percentileColor} bg-clip-text text-transparent`}>
              {percentile}%
            </h4>
            <p className="text-sm text-slate-400 mt-1">{percentileLabel}</p>
          </div>
          <div className="text-right">
            <p className="text-xs text-slate-400 mb-3">COMPARED TO ALL USERS</p>
            <div className="flex gap-1 justify-end">
              {[25, 50, 75, 100].map((p) => (
                <div
                  key={p}
                  className={`h-2 w-8 rounded ${
                    percentile >= p ? 'bg-emerald-500' : 'bg-slate-600'
                  }`}
                />
              ))}
            </div>
          </div>
        </div>
        <p className="text-xs text-slate-500">
          You scored higher than {percentile}% of candidates. Industry average is ~42.
        </p>
      </div>

      {/* Confidence Score */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <p className="text-sm font-medium text-slate-300">Confidence Level</p>
          <span className="text-sm font-bold text-emerald-400">{confidence}%</span>
        </div>
        <div className="w-full bg-slate-600 rounded-full h-2">
          <div
            className="h-2 rounded-full bg-gradient-to-r from-emerald-500 to-teal-400"
            style={{ width: `${confidence}%` }}
          />
        </div>
        <p className="text-xs text-slate-400 mt-2">
          Based on keyword match strength ({atsScoreData.keyword_match_percent?.toFixed(1)}%)
          and semantic similarity ({(atsScoreData.semantic_similarity_score ?? 0).toFixed(2)})
        </p>
      </div>

      {/* Algorithm Breakdown */}
      <div className="border-t border-slate-600 pt-4">
        <button
          onClick={() => setExpandAlgorithm(!expandAlgorithm)}
          className="w-full flex items-center justify-between hover:opacity-80 transition-opacity"
        >
          <p className="text-sm font-medium text-slate-300">Score Composition</p>
          {expandAlgorithm ? (
            <ChevronUp className="w-4 h-4 text-slate-400" />
          ) : (
            <ChevronDown className="w-4 h-4 text-slate-400" />
          )}
        </button>

        {expandAlgorithm && (
          <div className="mt-3 space-y-3">
            {Object.entries(breakdown).map(([factor, weight]) => (
              <div key={factor}>
                <div className="flex justify-between items-center mb-1">
                  <span className="text-sm text-slate-300 capitalize">{factor}</span>
                  <span className="text-sm font-semibold text-emerald-400">{weight}%</span>
                </div>
                <div className="w-full bg-slate-600 rounded-full h-1.5">
                  <div
                    className="h-1.5 rounded-full bg-gradient-to-r from-emerald-500 to-teal-400"
                    style={{ width: `${weight}%` }}
                  />
                </div>
              </div>
            ))}
            <p className="text-xs text-slate-400 mt-3">
              💡 Tip: To improve your score, focus on:
              <br />
              • <strong>Keywords</strong> (40%): Match job description terminology
              <br />
              • <strong>Format</strong> (30%): Use clear sections and bullet points
              <br />
              • <strong>Experience</strong> (20%): Highlight years and progression
              <br />• <strong>Structure</strong> (10%): Logical flow and readability
            </p>
          </div>
        )}
      </div>

      {/* Keyword Impact Data */}
      {keywordImpact.length > 0 && (
        <div className="border-t border-slate-600 pt-4">
          <button
            onClick={() => setExpandKeywords(!expandKeywords)}
            className="w-full flex items-center justify-between hover:opacity-80 transition-opacity"
          >
            <p className="text-sm font-medium text-slate-300">
              Keyword Impact ({keywordImpact.length} keywords)
            </p>
            {expandKeywords ? (
              <ChevronUp className="w-4 h-4 text-slate-400" />
            ) : (
              <ChevronDown className="w-4 h-4 text-slate-400" />
            )}
          </button>

          {expandKeywords && (
            <div className="mt-3 space-y-2">
              {keywordImpact.slice(0, 5).map((kw, idx) => (
                <div key={idx} className="bg-slate-600 rounded p-3 flex justify-between items-center">
                  <div className="flex-1">
                    <p className="text-sm font-medium text-white">{kw.keyword}</p>
                    <p className="text-xs text-slate-400">
                      Appears {kw.jd_frequency || 1}x in job description
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="text-sm font-bold text-emerald-400">+{kw.impact_percent}%</p>
                    <p className="text-xs text-slate-400">{Math.round((kw.confidence ?? 0.85) * 100)}% sure</p>
                  </div>
                </div>
              ))}
              {keywordImpact.length > 5 && (
                <p className="text-xs text-slate-400 text-center mt-2">
                  +{keywordImpact.length - 5} more keywords shown in full report
                </p>
              )}
            </div>
          )}
        </div>
      )}

      {/* Call to action: upgrade for full insights */}
      <div className="bg-gradient-to-r from-emerald-500/10 to-teal-500/10 border border-emerald-500/30 rounded p-3">
        <p className="text-sm text-emerald-300">
          ✨ <strong>Pro Tip:</strong> Upgrade to Pro to see all {(atsScoreData.recommended_keywords_to_add?.length ?? 0)} recommended keywords
          and step-by-step implementation guide.
        </p>
      </div>
    </div>
  );
};

export default CredibilityCard;
