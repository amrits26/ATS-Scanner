// frontend/src/components/CoachChatWidget.tsx
import React, { useState, useRef, useEffect } from 'react';
import { MessageCircle, X, Send, Loader2, Copy, ThumbsUp, ThumbsDown } from 'lucide-react';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  actionItems?: string[];
  confidence?: number;
}

export const CoachChatWidget: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([
    {
      role: 'assistant',
      content: 'Hi! I\'m your AI Resume Coach. Ask me anything about improving your resume, your bullet points, or career goals.',
    },
  ]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const sendMessage = async () => {
    if (!input.trim() || isLoading) return;

    const userMessage: Message = { role: 'user', content: input };
    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);
    setError(null);

    try {
      const resumeText = localStorage.getItem('current_resume') || '';
      if (!resumeText) {
        setError('Please upload a resume first to use the Coach.');
        setMessages(prev => [...prev, {
          role: 'assistant',
          content: '⚠️ I need your resume first. Please upload one and try again.'
        }]);
        setIsLoading(false);
        return;
      }

      const response = await fetch('/api/agent/coach', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('access_token') || ''}`,
        },
        body: JSON.stringify({
          question: input,
          resume_text: resumeText,
        }),
      });

      if (!response.ok) {
        throw new Error(`API error: ${response.statusText}`);
      }

      const data = await response.json();
      const assistantMessage: Message = {
        role: 'assistant',
        content: data.response?.response || 'I encountered an issue processing your request.',
        actionItems: data.response?.action_items,
        confidence: data.response?.confidence,
      };
      setMessages(prev => [...prev, assistantMessage]);
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Failed to connect to Coach.';
      setError(errorMsg);
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: `❌ Error: ${errorMsg}. Please try again or contact support.`
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    // Show brief feedback
  };

  return (
    <>
      {/* Floating button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="fixed bottom-6 right-6 bg-gradient-to-r from-blue-600 to-blue-700 hover:from-blue-700 hover:to-blue-800 text-white rounded-full p-4 shadow-lg transition-all z-50 hover:scale-110"
        title="Open Resume Coach"
      >
        {isOpen ? <X size={24} /> : <MessageCircle size={24} />}
      </button>

      {/* Chat window */}
      {isOpen && (
        <div className="fixed bottom-20 right-6 w-96 h-[600px] bg-white rounded-lg shadow-2xl flex flex-col z-40 border border-gray-200 overflow-hidden">
          {/* Header */}
          <div className="p-4 border-b bg-gradient-to-r from-blue-600 to-blue-700 text-white rounded-t-lg">
            <h3 className="font-bold text-lg">AI Resume Coach</h3>
            <p className="text-xs opacity-90">Get personalized feedback on your resume</p>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-4 space-y-4 bg-gray-50">
            {messages.map((msg, i) => (
              <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div className={`max-w-[85%] p-3 rounded-lg ${
                  msg.role === 'user'
                    ? 'bg-blue-600 text-white rounded-br-none'
                    : 'bg-white text-gray-800 border border-gray-200 rounded-bl-none shadow-sm'
                }`}>
                  <p className="text-sm whitespace-pre-wrap">{msg.content}</p>

                  {msg.actionItems && msg.actionItems.length > 0 && (
                    <div className="mt-2 pt-2 border-t border-gray-200">
                      <p className="text-xs font-semibold text-gray-600 mb-1">Action Items:</p>
                      <ul className="text-xs space-y-1">
                        {msg.actionItems.map((item, j) => (
                          <li key={j} className="flex items-start gap-2">
                            <span className="text-blue-500 font-bold">•</span>
                            <span>{item}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {msg.confidence && msg.role === 'assistant' && (
                    <div className="mt-2 pt-2 border-t border-gray-200">
                      <p className="text-xs text-gray-500">Confidence: {msg.confidence}%</p>
                    </div>
                  )}

                  {msg.role === 'assistant' && (
                    <div className="mt-2 flex gap-2">
                      <button
                        onClick={() => copyToClipboard(msg.content)}
                        className="p-1 hover:bg-gray-100 rounded transition-colors"
                        title="Copy"
                      >
                        <Copy size={14} className="text-gray-500" />
                      </button>
                      <button
                        onClick={() => console.log('Helpful')}
                        title="Helpful"
                        className="p-1 hover:bg-gray-100 rounded transition-colors"
                      >
                        <ThumbsUp size={14} className="text-gray-500" />
                      </button>
                      <button
                        onClick={() => console.log('Not helpful')}
                        title="Not helpful"
                        className="p-1 hover:bg-gray-100 rounded transition-colors"
                      >
                        <ThumbsDown size={14} className="text-gray-500" />
                      </button>
                    </div>
                  )}
                </div>
              </div>
            ))}

            {isLoading && (
              <div className="flex justify-start">
                <div className="bg-white border border-gray-200 p-3 rounded-lg rounded-bl-none">
                  <Loader2 className="animate-spin text-blue-600" size={16} />
                </div>
              </div>
            )}

            {error && (
              <div className="flex justify-center">
                <div className="bg-red-50 text-red-700 text-xs p-2 rounded">
                  {error}
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* Input */}
          <div className="p-4 border-t bg-white">
            <form
              onSubmit={(e) => { e.preventDefault(); sendMessage(); }}
              className="flex gap-2"
            >
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Ask me anything..."
                className="flex-1 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                disabled={isLoading}
              />
              <button
                type="submit"
                disabled={isLoading || !input.trim()}
                className="bg-blue-600 hover:bg-blue-700 text-white p-2 rounded-md disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                <Send size={18} />
              </button>
            </form>
            <p className="text-xs text-gray-500 mt-2">💡 Tip: Ask about specific bullets, keywords, or how to improve your score</p>
          </div>
        </div>
      )}
    </>
  );
};

export default CoachChatWidget;
