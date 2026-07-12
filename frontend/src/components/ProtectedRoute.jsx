import { Navigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

export function ProtectedRoute({ children }) {
  const { isAuthenticated, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div
        data-ptheme="dark"
        className="flex flex-col items-center justify-center min-h-screen gap-4 bg-[#131a22]"
      >
        <img
          src="/Amazon_Alexa_blue_logo.svg"
          alt="Amazon Alexa"
          className="h-12 w-12 opacity-90"
        />
        <div className="w-10 h-10 border-4 border-[var(--pp-accent)] border-t-transparent rounded-full animate-spin" />
        <p className="text-sm font-medium text-[var(--pp-muted)]">Loading Awaas AI…</p>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return children;
}
