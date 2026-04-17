/**
 * useTrainingLogger – Fire-and-forget hook for logging agent interactions.
 *
 * Sends user accept/edit/reject signals to the training pipeline so the
 * RLHF loop can learn from real usage patterns.
 */

import { useCallback } from 'react';

interface LogInteractionParams {
  agentType: string;
  jobId?: string;
  inputContext: Record<string, unknown>;
  agentOutput: Record<string, unknown>;
  userAction: 'accepted' | 'edited' | 'rejected' | 'applied';
  userEditedOutput?: Record<string, unknown>;
  rating?: number;
}

export function useTrainingLogger() {
  const getToken = () => localStorage.getItem('access_token') || '';

  const logInteraction = useCallback(async (params: LogInteractionParams) => {
    const token = getToken();
    if (!token) return;

    try {
      await fetch('/api/training/log', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          agent_type: params.agentType,
          job_id: params.jobId,
          input_context: params.inputContext,
          agent_output: params.agentOutput,
          user_action: params.userAction,
          user_edited_output: params.userEditedOutput,
          rating: params.rating,
        }),
      });
    } catch (error) {
      // Fire-and-forget — don't block UI on training log failures
      console.warn('Training log failed:', error);
    }
  }, []);

  return { logInteraction };
}
