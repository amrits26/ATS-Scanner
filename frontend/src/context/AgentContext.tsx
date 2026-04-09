// frontend/src/context/AgentContext.tsx
import React, { createContext, useContext, useState, ReactNode } from 'react';

export interface AgentState {
  isLoading: boolean;
  error: string | null;
  sessionId: string | null;
  lastExecutionTime: number | null;
  totalCostCents: number;
}

export interface AgentContextType {
  coach: AgentState;
  tailor: AgentState;
  interview: AgentState;
  setCoachState: (state: Partial<AgentState>) => void;
  setTailorState: (state: Partial<AgentState>) => void;
  setInterviewState: (state: Partial<AgentState>) => void;
  resetAll: () => void;
}

const defaultState: AgentState = {
  isLoading: false,
  error: null,
  sessionId: null,
  lastExecutionTime: null,
  totalCostCents: 0,
};

const AgentContext = createContext<AgentContextType | undefined>(undefined);

export const AgentProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [coach, setCoach] = useState<AgentState>(defaultState);
  const [tailor, setTailor] = useState<AgentState>(defaultState);
  const [interview, setInterview] = useState<AgentState>(defaultState);

  const setCoachState = (state: Partial<AgentState>) => {
    setCoach(prev => ({ ...prev, ...state }));
  };

  const setTailorState = (state: Partial<AgentState>) => {
    setTailor(prev => ({ ...prev, ...state }));
  };

  const setInterviewState = (state: Partial<AgentState>) => {
    setInterview(prev => ({ ...prev, ...state }));
  };

  const resetAll = () => {
    setCoach(defaultState);
    setTailor(defaultState);
    setInterview(defaultState);
  };

  const value: AgentContextType = {
    coach,
    tailor,
    interview,
    setCoachState,
    setTailorState,
    setInterviewState,
    resetAll,
  };

  return <AgentContext.Provider value={value}>{children}</AgentContext.Provider>;
};

export const useAgentContext = (): AgentContextType => {
  const context = useContext(AgentContext);
  if (!context) {
    throw new Error('useAgentContext must be used within AgentProvider');
  }
  return context;
};
