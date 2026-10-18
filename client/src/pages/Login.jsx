import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import Header from "../components/Header";
import Footer from "../components/Footer";
import { loginUser } from "../services/api";
import { useAuth } from "../context/AuthContext";

export default function Login() {
  const [role, setRole] = useState("passenger");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const navigate = useNavigate();
  const { login } = useAuth();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");

    if ((role === "passenger" && !phone) || (role !== "passenger" && !email)) {
      setError("Please enter your credentials");
      return;
    }
    if (!password) {
      setError("Please enter password");
      return;
    }

    try {
      setLoading(true);

      // Construct payload based on role
      const payload =
        role === "passenger"
          ? { role, phone, password }
          : { role, email, password };

      const data = await loginUser(payload);

      login({
        userId: data.user_id,
        role: data.role,
        name: data.name,
        token: data.token,
      });

      // Navigate based on role
      if (data.role === "passenger") navigate("/passenger/dashboard");
      else if (data.role === "conductor") navigate("/conductor/dashboard");
      else navigate("/admin/dashboard");
    } catch (err) {
      setError(err.message || "Login failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen flex-col bg-slate-50">
      <Header />
      <main className="flex-1 flex items-center justify-center px-4 py-10">
        <div className="w-full max-w-md rounded-2xl bg-white p-8 shadow border">
          <h1 className="text-center text-2xl font-semibold">BMTC Login</h1>
          <p className="mt-2 text-center text-sm text-slate-500">
            Login as Passenger, Conductor, or Admin
          </p>

          {/* Role selection */}
          <div className="mt-6">
            <p className="text-sm font-medium mb-2">Login as</p>
            <div className="flex gap-6 text-sm">
              {["passenger", "conductor", "admin"].map((r) => (
                <label key={r} className="flex items-center gap-2">
                  <input
                    type="radio"
                    value={r}
                    checked={role === r}
                    onChange={() => setRole(r)}
                  />
                  <span className="capitalize">{r}</span>
                </label>
              ))}
            </div>
          </div>

          {/* Login form */}
          <form onSubmit={handleSubmit} className="mt-6 space-y-4">
            {role === "passenger" ? (
              <input
                type="text"
                placeholder="Phone Number"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                className="w-full rounded-lg border px-3 py-2 text-sm"
              />
            ) : (
              <input
                type="email"
                placeholder="Email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full rounded-lg border px-3 py-2 text-sm"
              />
            )}

            <input
              type="password"
              placeholder="Password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-lg border px-3 py-2 text-sm"
            />

            {error && <p className="text-sm text-red-600">{error}</p>}

            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-lg bg-indigo-600 py-2.5 text-white font-semibold"
            >
              {loading ? "Logging in..." : "Login"}
            </button>
          </form>

          <p className="mt-4 text-center text-xs text-slate-500">
            New Passenger?{" "}
            <Link to="/signup" className="text-indigo-600 hover:underline">
              Register here
            </Link>
          </p>
        </div>
      </main>
      <Footer />
    </div>
  );
}
