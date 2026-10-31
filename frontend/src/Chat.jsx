import { useState, useRef, useEffect } from 'react';
import api from './api';
import { ArrowLeft, Send, Sparkles, Info, FileText, ChevronDown, Check, Copy } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

export default function Chat() {
  const navigate = useNavigate();
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [copiedIdx, setCopiedIdx] = useState(null);
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isLoading]);

  const handleSend = async (e) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;

    const userQuery = input.trim();
    setInput('');
    setMessages(prev => [...prev, { role: 'user', content: userQuery }]);
    setIsLoading(true);

    try {
      const res = await api.post('/api/chat/', { query: userQuery });
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: res.data.response,
        sources: res.data.sources
      }]);
    } catch {
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: 'Failed to connect to the AI engine. Please verify the backend is running.',
        isError: true
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  const copyToClipboard = (text, idx) => {
    navigator.clipboard.writeText(text);
    setCopiedIdx(idx);
    setTimeout(() => setCopiedIdx(null), 2000);
  };

  const suggestions = [
    "Summarize all uploaded documents",
    "List all vendors mentioned in my files",
  ];

  const resetChat = async () => {
    try {
      await api.post('/api/chat/reset');
      setMessages([]);
    } catch {
      setMessages(prev => [...prev, { role: 'assistant', content: 'Could not reset conversation. Please retry.', isError: true }]);
    }
  };

  return (
    <div className="flex flex-col h-screen bg-background">
      {/* ─── Header ─── */}
      <header className="blur-header sticky top-0 z-20 px-6 py-4 flex items-center justify-between animate-fade-in">
        <div className="flex items-center gap-4">
          <button
            onClick={() => navigate('/dashboard')}
            className="p-2 hover:bg-surface rounded-full transition-colors text-charcoal-600"
          >
            <ArrowLeft className="h-5 w-5" strokeWidth={1.5} />
          </button>
          <div>
            <h1 className="text-[15px] font-semibold tracking-tight text-charcoal-900">Assistant</h1>
          </div>
        </div>
        <div className="flex items-center gap-2 px-3 py-1 bg-surface rounded-full">
          <div className="w-1.5 h-1.5 rounded-full bg-green-500"></div>
          <button onClick={resetChat} disabled={isLoading} className="text-[11px] font-semibold text-charcoal-600">Reset chat</button>
        </div>
      </header>

      {/* ─── Chat Area ─── */}
      <div className="flex-1 overflow-y-auto px-4 py-8">
        <div className="max-w-[700px] mx-auto space-y-6">
          
          {/* Empty State */}
          {messages.length === 0 && !isLoading && (
            <div className="mt-20 flex flex-col items-center animate-fade-in stagger-1">
              <div className="w-16 h-16 bg-surface rounded-full flex items-center justify-center mb-6">
                <Sparkles className="h-6 w-6 text-charcoal-900" strokeWidth={1.5} />
              </div>
              <h2 className="text-[20px] font-semibold tracking-tight text-charcoal-900 mb-2">How can I help you today?</h2>
              <p className="text-[14px] text-charcoal-400 text-center max-w-sm mb-10">
                Ask questions about your uploaded documents or financial data.
              </p>

              <div className="flex gap-3 w-full animate-fade-in stagger-2">
                {suggestions.map((s, i) => (
                  <button
                    key={i}
                    onClick={() => { setInput(s); inputRef.current?.focus(); }}
                    className="flex-1 text-left p-4 bg-surface hover:bg-surfaceHover border border-transparent rounded-2xl transition-colors text-[14px] text-charcoal-900 font-medium"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Messages */}
          {messages.map((msg, idx) => (
            <div key={idx} className={`flex gap-3 animate-spring-up ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              
              {/* Avatar Assistant */}
              {msg.role === 'assistant' && (
                <div className="flex-shrink-0 w-8 h-8 rounded-full bg-charcoal-900 flex items-center justify-center mt-1">
                  <Sparkles className="h-4 w-4 text-white" strokeWidth={1.5} />
                </div>
              )}

              <div className={`max-w-[80%] ${msg.role === 'user' ? 'order-first' : ''}`}>
                <div className={`px-5 py-3.5 rounded-2xl text-[15px] leading-relaxed ${
                  msg.role === 'user'
                    ? 'bg-surface text-charcoal-900 rounded-br-sm'
                    : msg.isError
                      ? 'bg-red-50 text-red-600 rounded-bl-sm border border-red-100'
                      : 'bg-white border border-gray-200/60 text-charcoal-900 rounded-bl-sm shadow-sm'
                }`}>
                  <p className="whitespace-pre-wrap">{msg.content}</p>
                </div>

                {/* Assistant Tools */}
                {msg.role === 'assistant' && !msg.isError && (
                  <div className="flex items-center gap-2 mt-2 ml-1">
                    <button
                      onClick={() => copyToClipboard(msg.content, idx)}
                      className="text-[12px] font-medium text-charcoal-400 hover:text-charcoal-900 transition-colors flex items-center gap-1"
                    >
                      {copiedIdx === idx ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
                      {copiedIdx === idx ? 'Copied' : 'Copy'}
                    </button>
                  </div>
                )}

                {/* Sources */}
                {msg.sources && msg.sources.length > 0 && (
                  <SourceDropdown sources={msg.sources} />
                )}
              </div>
            </div>
          ))}

          {/* Loading state */}
          {isLoading && (
            <div className="flex gap-3 animate-fade-in">
              <div className="flex-shrink-0 w-8 h-8 rounded-full bg-charcoal-900 flex items-center justify-center mt-1">
                <Sparkles className="h-4 w-4 text-white" strokeWidth={1.5} />
              </div>
              <div className="bg-white border border-gray-200/60 rounded-2xl rounded-bl-sm px-5 py-4 shadow-sm">
                <div className="typing-dots"><span /><span /><span /></div>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* ─── Input ─── */}
      <div className="p-4 bg-background">
        <div className="max-w-[700px] mx-auto relative animate-fade-in">
          <form onSubmit={handleSend} className="relative">
            <input
              ref={inputRef}
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Message Assistant..."
              className="w-full pl-5 pr-14 py-3.5 bg-surface border border-transparent rounded-full text-[15px] text-charcoal-900 placeholder-charcoal-400 transition-all focus:bg-white focus:border-charcoal-900 focus:outline-none focus:ring-1 focus:ring-charcoal-900"
              disabled={isLoading}
            />
            <button
              type="submit"
              disabled={!input.trim() || isLoading}
              className="absolute right-2 top-1/2 -translate-y-1/2 p-2 bg-charcoal-900 text-white rounded-full disabled:opacity-30 disabled:bg-charcoal-400 active:scale-95 transition-all"
            >
              <Send className="h-4 w-4" strokeWidth={2} />
            </button>
          </form>
          <div className="text-center mt-3">
            <span className="text-[11px] text-charcoal-400 font-medium">FinSentinel runs 100% locally and privately.</span>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ─── Minimal Source Dropdown ─── */
function SourceDropdown({ sources }) {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <div className="mt-2 ml-1">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-1.5 text-[12px] font-medium text-charcoal-600 hover:text-charcoal-900 transition-colors"
      >
        <Info className="h-3.5 w-3.5" strokeWidth={1.5} />
        {sources.length} Sources
        <ChevronDown className={`h-3.5 w-3.5 transition-transform duration-200 ${isOpen ? 'rotate-180' : ''}`} />
      </button>
      
      {isOpen && (
        <div className="mt-3 space-y-2 animate-scale-in origin-top">
          {sources.slice(0, 3).map((s, i) => (
            <div key={i} className="bg-surface rounded-xl p-3 text-[12px]">
              <div className="flex items-center gap-2 mb-1">
                <FileText className="h-3.5 w-3.5 text-charcoal-400" strokeWidth={1.5} />
                <span className="font-semibold text-charcoal-900">{s.file_name}{s.page ? ` · Page ${s.page}` : ''}</span>
              </div>
              <p className="text-charcoal-600 leading-relaxed line-clamp-2">{s.text}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
