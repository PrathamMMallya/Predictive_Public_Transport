import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function ProtectedRoute({ children, requiredRole }) {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    // while checking localStorage
    return <div className="p-4 text-center">Loading...</div>;
  }

  if (!user) {
    // not logged in -> send to login, remember where they wanted to go
    return (
      <Navigate
        to="/login"
        replace
        state={{ from: location.pathname }}
      />
    );
  }

  if (requiredRole && user.role !== requiredRole) {
    // wrong role -> send to their own dashboard
    if (user.role === "conductor") return <Navigate to="/conductor/dashboard" replace />;
    if (user.role === "passenger") return <Navigate to="/passenger/dashboard" replace />;
    if (user.role === "admin") return <Navigate to="/admin/dashboard" replace />;
  }

  return children;
}
