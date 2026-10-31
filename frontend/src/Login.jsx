import { useState } from 'react';
import { useAuth } from './AuthContext';
import { Briefcase, ArrowRight } from 'lucide-react';

export default function Login() {
  const { login, register } = useAuth();
  const [isLogin, setIsLogin] = useState(true);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setIsLoading(true);
    try {
      if (isLogin) {
        await login(username, password);
      } else {
        await register(username, password);
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Authentication failed. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-background flex flex-col items-center justify-center p-4 selection:bg-surfaceHover">
      <div className="w-full max-w-[340px] animate-scale-in">
        
        {/* Header */}
        <div className="text-center mb-10 animate-fade-in stagger-1">
          <div className="inline-flex items-center justify-center w-12 h-12 rounded-[14px] bg-charcoal-900 text-white mb-6 shadow-apple">
            <Briefcase className="h-6 w-6" strokeWidth={1.5} />
          </div>
          <h1 className="text-[28px] font-semibold tracking-tight text-charcoal-900 mb-2">FinSentinel</h1>
          <p className="text-[15px] text-charcoal-400">
            {isLogin ? 'Sign in to continue.' : 'Create your account.'}
          </p>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-4 animate-fade-in stagger-2">
          {error && (
            <div className="text-[13px] text-red-500 bg-red-50 px-4 py-3 rounded-xl font-medium border border-red-100">
              {error}
            </div>
          )}

          <div className="space-y-3">
            <input
              type="text"
              required
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="input-minimal"
              placeholder="Username"
            />
            <input
              type="password"
              required
              minLength={isLogin ? undefined : 12}
              maxLength={72}
              autoComplete={isLogin ? 'current-password' : 'new-password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="input-minimal"
              placeholder="Password"
            />
          </div>

          <button
            type="submit"
            disabled={isLoading}
            className="btn-minimal w-full mt-2 disabled:opacity-50"
          >
            {isLoading ? (
              <div className="typing-dots"><span /><span /><span /></div>
            ) : (
              <>
                {isLogin ? 'Sign In' : 'Continue'}
                <ArrowRight className="h-4 w-4 opacity-50" strokeWidth={2} />
              </>
            )}
          </button>
        </form>

        <div className="mt-8 text-center animate-fade-in stagger-3">
          <button
            onClick={() => { setIsLogin(!isLogin); setError(''); }}
            className="text-[14px] text-charcoal-600 hover:text-charcoal-900 transition-colors"
          >
            {isLogin ? "Don't have an account? Create one." : 'Already have an account? Sign in.'}
          </button>
        </div>
      </div>
    </div>
  );
}
