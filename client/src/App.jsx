import { BrowserRouter, Routes, Route } from "react-router-dom";
import Home from "./pages/Home";
import Login from "./pages/Login";
import Signup from "./pages/Signup";

import PassengerDashboard from "./pages/PassengerDashboard";
import ConductorDashboard from "./pages/ConductorDashboard";
import AdminDashboard from "./pages/AdminDashboard";

import { AuthProvider } from "./context/AuthContext";
import ProtectedRoute from "./components/ProtectedRoute";

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          {/* Public */}
          <Route path="/" element={<Home />} />
          <Route path="/login" element={<Login />} />
          <Route path="/signup" element={<Signup />} />

          {/* Passenger */}
          <Route
            path="/passenger/dashboard"
            element={
              <ProtectedRoute requiredRole="passenger">
                <PassengerDashboard />
              </ProtectedRoute>
            }
          />

          {/* Conductor */}
          <Route
            path="/conductor/dashboard"
            element={
              <ProtectedRoute requiredRole="conductor">
                <ConductorDashboard />
              </ProtectedRoute>
            }
          />

          {/* Admin */}
          <Route
            path="/admin/dashboard"
            element={
              <ProtectedRoute requiredRole="admin">
                <AdminDashboard />
              </ProtectedRoute>
            }
          />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
