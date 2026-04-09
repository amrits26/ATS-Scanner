// frontend/src/components/KeywordBoosterUpsell.tsx
import React from 'react';
import { TrendingUp, Lock, ArrowRight, Zap } from 'lucide-react';

interface KeywordBoosterProps {
  missingKeywords: string[];
  potentialScoreGain: number;
  currentScore?: number;
  onUpgrade: () => void;
  onDismiss?: () => void;
}

export const KeywordBoosterUpsell: React.FC<KeywordBoosterProps> = ({
  missingKeywords,
  potentialScoreGain,
  currentScore = 72,
  onUpgrade,
  onDismiss,
}) => {
  const projectedScore = currentScore + potentialScoreGain;

  return (
    <div className="relative overflow-hidden bg-gradient-to-br from-amber-50 via-orange-50 to-red-50 border-2 border-amber-200 rounded-xl p-6 shadow-lg">
      {/* Decorative elements */}
      <div className="absolute top-2 right-2 text-4xl opacity-10">⭐</div>
      <div className="absolute bottom-2 left-2 text-4xl opacity-10">⚡</div>

      <div className="relative z-10">
        {/* Header */}
        <div className="flex items-start justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className="bg-gradient-to-br from-amber-400 to-orange-500 p-3 rounded-full shadow-md">
              <TrendingUp className="text-white" size={24} />
            </div>
            <div>
              <h3 className="font-bold text-gray-900 text-lg">Unlock +{potentialScoreGain} Points</h3>
              <p className="text-sm text-amber-800">High-impact keywords found</p>
            </div>
          </div>
          {onDismiss && (
            <button
              onClick={onDismiss}
              className="text-gray-400 hover:text-gray-600 transition-colors"
            >
              ✕
            </button>
          )}
        </div>

        {/* Score Projection */}
        <div className="grid grid-cols-3 gap-3 mb-5">
          <div className="text-center">
            <p className="text-xs text-gray-600 font-semibold">Your Score</p>
            <p className="text-2xl font-bold text-gray-900">{currentScore}</p>
          </div>
          <div className="flex items-center justify-center">
            <ArrowRight className="text-amber-600" size={24} />
          </div>
          <div className="text-center">
            <p className="text-xs text-gray-600 font-semibold">Projected</p>
            <p className="text-2xl font-bold text-green-600">{projectedScore}</p>
          </div>
        </div>

        {/* Keywords */}
        <div className="mb-5">
          <p className="text-sm font-semibold text-gray-900 mb-3">Recruiter-demanded keywords you're missing:</p>
          <div className="flex flex-wrap gap-2">
            {missingKeywords.slice(0, 6).map((keyword, idx) => (
              <div
                key={idx}
                className="px-3 py-1.5 bg-white rounded-full text-sm font-semibold text-amber-900 shadow-sm border border-amber-200 hover:shadow-md transition-shadow"
              >
                {keyword}
              </div>
            ))}
            {missingKeywords.length > 6 && (
              <div className="px-3 py-1.5 bg-white rounded-full text-sm font-semibold text-amber-900 shadow-sm border border-amber-200">
                +{missingKeywords.length - 6} more
              </div>
            )}
          </div>
        </div>

        {/* Value Proposition */}
        <div className="grid grid-cols-2 gap-3 mb-5">
          <div className="p-3 bg-white bg-opacity-70 rounded-lg border border-amber-100">
            <p className="text-xs text-gray-600">Top 5% of Resumes</p>
            <p className="text-sm font-bold text-gray-900">Score 90+</p>
          </div>
          <div className="p-3 bg-white bg-opacity-70 rounded-lg border border-amber-100">
            <p className="text-xs text-gray-600">Increase Interviews</p>
            <p className="text-sm font-bold text-gray-900">+60% More Matches</p>
          </div>
        </div>

        {/* CTA */}
        <button
          onClick={onUpgrade}
          className="w-full flex items-center justify-center gap-2 px-6 py-3 bg-gradient-to-r from-amber-500 to-orange-600 hover:from-amber-600 hover:to-orange-700 text-white font-bold rounded-lg shadow-lg transition-all hover:shadow-xl active:scale-95"
        >
          <Zap size={20} />
          <span>Add Keywords & Boost Score</span>
          <Lock size={16} className="opacity-75" />
        </button>

        {/* Pricing & Terms */}
        <p className="text-center text-xs text-amber-900 mt-3 font-medium">
          🎁 One-time purchase • $4.99
        </p>
        <p className="text-center text-xs text-gray-600 mt-1">
          Includes AI rewrite + optimization tips
        </p>

        {/* Social Proof */}
        <div className="mt-4 pt-4 border-t border-amber-200">
          <p className="text-xs text-gray-700 text-center">
            ⭐ <span className="font-semibold">4.8/5</span> from 2,300+ users who boosted their score
          </p>
        </div>
      </div>
    </div>
  );
};

export default KeywordBoosterUpsell;
