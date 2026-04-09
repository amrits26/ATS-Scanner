// frontend/src/hooks/useAgentAPI.ts
import { useState, useCallback } from 'react';
import { useAgentContext } from '../context/AgentContext';

interface AgentAPIOptions {
  agentType: 'coach' | 'tailor' | 'interview';
}

interface CoachRequest {
  question: string;
  resume_text: string;
}

interface TailorRequest {
  resume_text: string;
  jd_url?: string;
  jd_text?: string;
}

interface InterviewRequest {
  job_title: string;
  company: string;
  resume_text: string;
}

export const useAgentAPI = () => {
  const context = useAgentContext();
  const [globalError, setGlobalError] = useState<string | null>(null);

  const getAuthToken = useCallback(() => {
    return localStorage.getItem('access_token') || '';
  }, []);

  const callCoach = useCallback(
    async (payload: CoachRequest) => {
      context.setCoachState({ isLoading: true, error: null });
      try {
        const response = await fetch('/api/agent/coach', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${getAuthToken()}`,
          },
          body: JSON.stringify(payload),
        });

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const data = await response.json();
        context.setCoachState({
          isLoading: false,
          sessionId: data.session_id,
          lastExecutionTime: data.execution_time_seconds,
          totalCostCents: (context.coach.totalCostCents || 0) + (data.gemini_cost_cents || 0),
        });
        return data;
      } catch (err) {
        const errorMsg = err instanceof Error ? err.message : 'Unknown error';
        context.setCoachState({ isLoading: false, error: errorMsg });
        setGlobalError(errorMsg);
        throw err;
      }
    },
    [context, getAuthToken]
  );

  const callTailor = useCallback(
    async (payload: TailorRequest) => {
      context.setTailorState({ isLoading: true, error: null });
      try {
        const response = await fetch('/api/agent/tailor', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${getAuthToken()}`,
          },
          body: JSON.stringify(payload),
        });

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const data = await response.json();
        context.setTailorState({
          isLoading: false,
          sessionId: data.session_id,
          lastExecutionTime: data.execution_time_seconds,
          totalCostCents: (context.tailor.totalCostCents || 0) + (data.gemini_cost_cents || 0),
        });
        return data;
      } catch (err) {
        const errorMsg = err instanceof Error ? err.message : 'Unknown error';
        context.setTailorState({ isLoading: false, error: errorMsg });
        setGlobalError(errorMsg);
        throw err;
      }
    },
    [context, getAuthToken]
  );

  const callInterview = useCallback(
    async (payload: InterviewRequest) => {
      context.setInterviewState({ isLoading: true, error: null });
      try {
        const response = await fetch('/api/agent/interview-prep', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${getAuthToken()}`,
          },
          body: JSON.stringify(payload),
        });

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const data = await response.json();
        context.setInterviewState({
          isLoading: false,
          sessionId: data.session_id,
          lastExecutionTime: data.execution_time_seconds,
          totalCostCents: (context.interview.totalCostCents || 0) + (data.gemini_cost_cents || 0),
        });
        return data;
      } catch (err) {
        const errorMsg = err instanceof Error ? err.message : 'Unknown error';
        context.setInterviewState({ isLoading: false, error: errorMsg });
        setGlobalError(errorMsg);
        throw err;
      }
    },
    [context, getAuthToken]
  );

  const resetErrors = useCallback(() => {
    setGlobalError(null);
    context.setCoachState({ error: null });
    context.setTailorState({ error: null });
    context.setInterviewState({ error: null });
  }, [context]);

  return {
    callCoach,
    callTailor,
    callInterview,
    globalError,
    resetErrors,
    agentStates: {
      coach: context.coach,
      tailor: context.tailor,
      interview: context.interview,
    },
  };
};

export default useAgentAPI;
