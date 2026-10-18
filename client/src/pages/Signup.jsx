import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import Header from "../components/Header";
import Footer from "../components/Footer";
import { signupUser, requestOtp } from "../services/api";

export default function Signup() {
  const navigate = useNavigate();

  const [role, setRole] = useState("passenger");
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [badgeId, setBadgeId] = useState("");
  const [depot, setDepot] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [otp, setOtp] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [strength, setStrength] = useState("");

  const getPasswordStrength = (pwd) => {
    if (pwd.length < 4) return "Too Weak";
    if (pwd.length < 7) return "Easy";
    if (pwd.length < 10) return "Medium";
    return "Strong";
  };

  const handlePasswordChange = (e) => {
    const val = e.target.value;
    setPassword(val);
    setStrength(getPasswordStrength(val));
  };

  const handleRequestOtp = async () => {
    setError("");
    try {
      await requestOtp({ role, phone, email });
      alert("OTP sent! Check console.");
    } catch (err) {
      setError(err.message || "Failed to send OTP");
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");

    if (password !== confirmPassword) {
      setError("Passwords do not match");
      return;
    }

    try {
      setLoading(true);
      const payload = { role, name, phone, email, badge_id: badgeId, depot, password, otp };
      await signupUser(payload);
      alert("Signup successful!");
      navigate("/login");
    } catch (err) {
      setError(err.message || "Signup failed");
    } finally {
      setLoading(false);
    }
  };

  const strengthColor = {
    "Too Weak": "red",
    "Easy": "orange",
    "Medium": "yellow",
    "Strong": "green",
  };

  return (
    <div className="flex min-h-screen flex-col bg-slate-50">
      <Header />
      <main className="flex-1 flex items-center justify-center px-4 py-10">
        <div className="w-full max-w-md rounded-2xl bg-white p-8 shadow border">
          <h1 className="text-center text-2xl font-semibold">BMTC User Registration</h1>
          <p className="mt-2 text-center text-sm text-slate-500">Passenger / Conductor / Admin</p>

          <div className="mt-4 flex justify-center gap-6 text-sm">
            {["passenger","conductor","admin"].map(r => (
              <label key={r} className="flex items-center gap-2">
                <input type="radio" value={r} checked={role===r} onChange={()=>setRole(r)} />
                <span className="capitalize">{r}</span>
              </label>
            ))}
          </div>

          <form onSubmit={handleSubmit} className="mt-6 space-y-3">
            <input placeholder="Full Name" value={name} onChange={e=>setName(e.target.value)} className="input w-full" />
            <input placeholder="Phone Number" value={phone} onChange={e=>setPhone(e.target.value)} className="input w-full" />
            {(role==="conductor" || role==="admin") && (
              <input placeholder="Email" value={email} onChange={e=>setEmail(e.target.value)} className="input w-full" />
            )}
            {role==="conductor" && (
              <>
                <input placeholder="Badge ID" value={badgeId} onChange={e=>setBadgeId(e.target.value)} className="input w-full" />
                <input placeholder="Depot Number" value={depot} onChange={e=>setDepot(e.target.value)} className="input w-full" />
              </>
            )}
            <input type="password" placeholder="Password" value={password} onChange={handlePasswordChange} className="input w-full" />
            {password && (
              <p style={{ color: strengthColor[strength], fontWeight: 'bold' }}>Strength: {strength}</p>
            )}
            <input type="password" placeholder="Confirm Password" value={confirmPassword} onChange={e=>setConfirmPassword(e.target.value)} className="input w-full" />
            <input placeholder="OTP" value={otp} onChange={e=>setOtp(e.target.value)} className="input w-full" />

            <button type="button" onClick={handleRequestOtp} className="w-full rounded bg-gray-400 py-2 text-white font-semibold">
              Request OTP
            </button>
            {error && <p className="text-red-600">{error}</p>}
            <button type="submit" disabled={loading} className="w-full rounded bg-indigo-600 py-2 text-white font-semibold">
              {loading ? "Registering..." : "Create Account"}
            </button>
          </form>

          <p className="mt-4 text-center text-xs">
            Already registered? <Link to="/login" className="text-indigo-600">Login</Link>
          </p>
        </div>
      </main>
      <Footer />
    </div>
  );
}
