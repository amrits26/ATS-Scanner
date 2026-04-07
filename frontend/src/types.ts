export interface SectionImprovements {
  summary: string;
  experience: string;
  skills: string;
}

export interface ATSScoreResponse {
  keyword_match_percent: number;
  semantic_similarity_score: number;
  final_ats_score: number;
  missing_keywords: string[];
  recommended_keywords_to_add: string[];
  // Phase 6: Credibility Layer
  percentile_rank?: number; // 0-100, where user ranks
  confidence_score?: number; // 0-100, confidence in score
  algorithm_breakdown?: Record<string, number>; // {"keywords": 40, "format": 30, ...}
  keyword_impact_data?: Array<{
    keyword: string;
    impact_percent: number;
    confidence: number;
    jd_frequency?: number;
  }>;
}

export interface JobDescriptionAnalysis {
  required_skills: string[];
  preferred_skills: string[];
  responsibilities: string[];
  keywords: string[];
  tools: string[];
  experience_level: string;
}

export interface WritingFeedback {
  weak_verbs_detected: string[];
  bullets_without_metrics: string[];
  passive_voice_phrases: string[];
  readability_score: number;
  sections_detected: string[];
}

export interface FullOptimizationResult {
  optimized_resume: string;
  section_improvements: SectionImprovements;
  ats_score: ATSScoreResponse;
  jd_analysis: JobDescriptionAnalysis;
  writing_feedback: WritingFeedback | null;
  chart_paths: Record<string, string>;
}

// New comprehensive analysis models
export interface SkillGapAnalysis {
  matched_skills: string[];
  missing_skills: string[];
  gap_score: number;
  match_count: number;
  total_required: number;
}

export interface ResumeQualityScore {
  overall_score: number;
  readability_score: number;
  formatting_score: number;
  content_score: number;
  keyword_density_score: number;
  feedback: string[];
}

export interface KeywordHeatmapData {
  keywords: string[];
  frequencies: number[];
  importance_scores: number[];
}

export interface ComprehensiveAnalysisResult {
  original_resume: string;
  optimized_resume: string;
  ats_score: ATSScoreResponse;
  jd_analysis: JobDescriptionAnalysis;
  skill_gap: SkillGapAnalysis;
  resume_quality: ResumeQualityScore;
  keyword_heatmap: KeywordHeatmapData;
  writing_feedback: WritingFeedback | null;
  chart_paths: Record<string, string>;
}

export type UserTierEnum = "free" | "pro";

export interface UserProfile {
  id: string;
  email: string;
  full_name?: string;
  tier: UserTierEnum;
  scans_this_month: number;
  scan_limit: number;
  created_at: string;
}
