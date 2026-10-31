import { useState, useEffect, useRef, useCallback } from 'react';
import api from './api';
import { useAuth } from './AuthContext';
import {
  FileText, Trash2, LogOut, MessageSquare,
  Plus, FolderOpen, Loader2, Search, X
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';

export default function Dashboard() {
  const { user, logout } = useAuth();
  const [documents, setDocuments] = useState([]);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [error, setError] = useState('');
  const fileInputRef = useRef(null);
  const navigate = useNavigate();

  const fetchDocuments = useCallback(async () => {
    try {
      const res = await api.get('/api/documents/list');
      setDocuments(res.data.documents || []);
    } catch (err) {
      console.error('Failed to fetch documents', err);
    }
  }, []);

  useEffect(() => {
    fetchDocuments();
  }, [fetchDocuments]);

  const handleFileUpload = async (e) => {
    const files = e.target.files;
    if (!files.length) return;

    setIsUploading(true);
    setError('');
    setUploadProgress(Array.from(files).map(f => ({ name: f.name, status: 'uploading' })));
    
    const formData = new FormData();
    for (let i = 0; i < files.length; i++) {
      formData.append('files', files[i]);
    }

    try {
      const response = await api.post('/api/documents/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      setUploadProgress(response.data.map(item => ({ name: item.filename, status: item.status, message: item.message })));
      fetchDocuments();
    } catch (err) {
      setError(err.response?.data?.detail || 'Upload failed. Please retry.');
      setUploadProgress([]);
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const handleDelete = async (filename) => {
    try {
      await api.delete(`/api/documents/${encodeURIComponent(filename)}`);
      fetchDocuments();
    } catch (err) {
      setError(err.response?.data?.detail || 'Deletion failed. Please retry.');
    }
  };

  const filteredDocs = documents.filter(d =>
    d.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="min-h-screen bg-background flex text-charcoal-900">
      
      {/* ─── Sidebar ─── */}
      <aside className="w-[260px] bg-surface flex flex-col border-r border-gray-200/60 animate-fade-in">
        
        {/* Brand */}
        <div className="p-6 pb-8 flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-charcoal-900 flex items-center justify-center text-white">
            <FileText className="h-4 w-4" strokeWidth={2} />
          </div>
          <span className="font-semibold tracking-tight text-[15px]">FinSentinel</span>
        </div>

        {/* Navigation */}
        <nav className="flex-1 px-4 space-y-1">
          <button className="w-full flex items-center justify-between px-3 py-2 bg-white rounded-lg text-[14px] font-medium shadow-sm border border-black/5 text-charcoal-900">
            <div className="flex items-center gap-3">
              <FolderOpen className="h-[18px] w-[18px] text-charcoal-600" strokeWidth={1.5} />
              Documents
            </div>
            <span className="text-[11px] text-charcoal-400 font-semibold">{documents.length}</span>
          </button>

          <button
            onClick={() => navigate('/chat')}
            className="w-full flex items-center gap-3 px-3 py-2 text-[14px] text-charcoal-600 hover:bg-surfaceHover rounded-lg font-medium transition-colors"
          >
            <MessageSquare className="h-[18px] w-[18px]" strokeWidth={1.5} />
            Chat Assistant
          </button>
        </nav>

        {/* User Footer */}
        <div className="p-4 mt-auto">
          <div className="flex items-center justify-between p-3 rounded-xl hover:bg-surfaceHover transition-colors group cursor-pointer" onClick={logout}>
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-full bg-white border border-black/5 flex items-center justify-center text-charcoal-900 font-semibold text-xs shadow-sm uppercase">
                {user?.username?.[0]}
              </div>
              <span className="text-[13px] font-medium text-charcoal-900">{user?.username}</span>
            </div>
            <LogOut className="h-4 w-4 text-charcoal-400 opacity-0 group-hover:opacity-100 transition-opacity" strokeWidth={1.5} />
          </div>
        </div>
      </aside>

      {/* ─── Main Content ─── */}
      <main className="flex-1 flex flex-col h-screen overflow-hidden">
        
        {/* Header */}
        <header className="px-10 py-8 flex items-center justify-between animate-fade-in stagger-1">
          <h1 className="text-[24px] font-semibold tracking-tight">Documents</h1>
          <div>
            <input
              type="file"
              multiple
              className="hidden"
              ref={fileInputRef}
              onChange={handleFileUpload}
              accept=".pdf,.png,.jpg,.jpeg,.txt,.csv,.json,.xml"
            />
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={isUploading}
              className="btn-minimal text-[14px] px-5 py-2.5"
            >
              <Plus className="h-4 w-4" strokeWidth={2} />
              {isUploading ? 'Uploading...' : 'Add Files'}
            </button>
          </div>
        </header>

        {/* List Area */}
        <div className="flex-1 px-10 pb-10 overflow-y-auto animate-fade-in stagger-2">
          {error && <p role="alert" className="mb-4 text-red-600">{error}</p>}
          
          {/* Search */}
          {documents.length > 0 && (
            <div className="relative mb-6 max-w-md">
              <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-charcoal-400" strokeWidth={1.5} />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search documents..."
                className="w-full pl-10 pr-10 py-2.5 bg-surface border border-transparent rounded-lg text-[14px] placeholder-charcoal-400 focus:bg-white focus:border-charcoal-900 focus:outline-none transition-all"
              />
              {searchQuery && (
                <button onClick={() => setSearchQuery('')} className="absolute right-3 top-1/2 -translate-y-1/2 text-charcoal-400 hover:text-charcoal-900">
                  <X className="h-4 w-4" />
                </button>
              )}
            </div>
          )}

          {/* Uploading Status */}
          {uploadProgress.length > 0 && (
            <div className="mb-6 space-y-2">
              {uploadProgress.map((p, i) => (
                <div key={i} className="flex items-center gap-3 text-[13px] text-charcoal-600 bg-surface px-4 py-3 rounded-lg border border-black/5 animate-fade-in">
                  {p.status === 'uploading' && <Loader2 className="h-4 w-4 animate-spin" />}
                  <span role={p.status === 'error' ? 'alert' : 'status'}>
                    <span className="font-medium text-charcoal-900">{p.name}</span>: {p.message || 'Processing...'}
                  </span>
                </div>
              ))}
            </div>
          )}

          {/* Empty State */}
          {filteredDocs.length === 0 && !isUploading ? (
            <div className="mt-20 text-center flex flex-col items-center animate-fade-in stagger-3">
              <div className="w-16 h-16 bg-surface rounded-full flex items-center justify-center mb-4">
                <FileText className="h-6 w-6 text-charcoal-400" strokeWidth={1.5} />
              </div>
              <h3 className="text-[16px] font-semibold text-charcoal-900">No documents found</h3>
              <p className="text-[14px] text-charcoal-400 mt-1 max-w-sm">
                Upload your financial files, and we'll automatically index them for AI search.
              </p>
            </div>
          ) : (
            <div className="bg-white border border-gray-200/60 rounded-xl overflow-hidden shadow-sm animate-fade-in stagger-3">
              <ul className="divide-y divide-gray-100">
                {filteredDocs.map((doc, idx) => (
                  <li key={idx} className="group flex items-center justify-between px-5 py-4 hover:bg-surface transition-colors">
                    <div className="flex items-center gap-4">
                      <FileText className="h-5 w-5 text-charcoal-400" strokeWidth={1.5} />
                      <div>
                        <p className="text-[14px] font-medium text-charcoal-900">{doc}</p>
                      </div>
                    </div>
                    <button
                      onClick={() => handleDelete(doc)}
                      className="text-charcoal-400 hover:text-red-500 p-2 rounded-lg opacity-0 group-hover:opacity-100 transition-all"
                      title="Delete document"
                    >
                      <Trash2 className="h-4 w-4" strokeWidth={1.5} />
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
