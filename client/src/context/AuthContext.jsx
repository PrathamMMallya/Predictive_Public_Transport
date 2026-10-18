import { createContext, useContext, useEffect, useState } from "react";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null); // { userId, role, name }
  const [token, setToken] = useState(null);
  const [loading, setLoading] = useState(true);

  // Load from localStorage on first render
  useEffect(() => {
    const stored = localStorage.getItem("eskill_auth");
    if (stored) {
      const parsed = JSON.parse(stored);
      setUser(parsed.user);
      setToken(parsed.token);
    }
    setLoading(false);
  }, []);

  function login(authData) {
    // authData: { userId, role, name, token }
    const newUser = {
      userId: authData.userId,
      role: authData.role,
      name: authData.name,
    };
    setUser(newUser);
    setToken(authData.token);
    localStorage.setItem(
      "eskill_auth",
      JSON.stringify({ user: newUser, token: authData.token })
    );
  }

  function logout() {
    setUser(null);
    setToken(null);
    localStorage.removeItem("eskill_auth");
  }

  const value = { user, token, loading, login, logout };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}
