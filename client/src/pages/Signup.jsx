
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
  const [success, setSuccess] = useState("");
  const [loading, setLoading] = useState(false);
  const [otpLoading, setOtpLoading] = useState(false);
  const [strength, setStrength] = useState("");

  const getPasswordStrength = (pwd) => {
    if (!pwd) return "";
    if (pwd.length < 4) return "Too Weak";
    if (pwd.length < 7) return "Easy";
    if (pwd.length < 10) return "Medium";
    return "Strong";
  };

  const handlePasswordChange = (e) => {
    const value = e.target.value;
    setPassword(value);
    setStrength(getPasswordStrength(value));
  };

  const validPhone = (value) => /^[6-9]\d{9}$/.test(value.trim());

  const validEmail = (value) =>
    /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim());

  const validateCommonFields = () => {
    if (!name.trim() || !/^[A-Za-z ]{3,}$/.test(name.trim())) {
      setError("Enter a valid full name using at least 3 letters.");
      return false;
    }

    if (!validPhone(phone)) {
      setError("Enter a valid 10-digit Indian mobile number.");
      return false;
    }

    if (
      (role === "conductor" || role === "admin") &&
      !validEmail(email)
    ) {
      setError("Enter a valid email address.");
      return false;
    }

    return true;
  };

  const handleRoleChange = (newRole) => {
    setRole(newRole);
    setError("");
    setSuccess("");
    setOtp("");
  };

  const handleRequestOtp = async () => {
    setError("");
    setSuccess("");

    if (!validPhone(phone)) {
      setError("Enter a valid 10-digit Indian mobile number first.");
      return;
    }

    if (
      (role === "conductor" || role === "admin") &&
      !validEmail(email)
    ) {
      setError("Enter a valid email address first.");
      return;
    }

    try {
      setOtpLoading(true);

      const result = await requestOtp({
        role,
        phone: phone.trim(),
        email: email.trim().toLowerCase(),
      });

      setOtp("");

      setSuccess(
        result.message ||
          "OTP generated. Check the terminal running the Flask backend on port 5000."
      );
    } catch (err) {
      setError(err.message || "Failed to generate OTP.");
    } finally {
      setOtpLoading(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setSuccess("");

    if (!validateCommonFields()) return;

    if (role === "conductor" && !badgeId.trim()) {
      setError("Enter your conductor Badge ID.");
      return;
    }

    if (role === "conductor" && !depot.trim()) {
      setError("Enter your depot number.");
      return;
    }

    if (!password) {
      setError("Enter a password.");
      return;
    }

    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    if (!/^\d{6}$/.test(otp.trim())) {
      setError("Enter the six-digit OTP from the Flask backend terminal.");
      return;
    }

    try {
      setLoading(true);

      const payload = {
        role,
        name: name.trim(),
        phone: phone.trim(),
        email: email.trim().toLowerCase(),
        badge_id: badgeId.trim(),
        depot: depot.trim(),
        password,
        otp: otp.trim(),
      };

      const result = await signupUser(payload);

      setSuccess(result.message || "Signup successful!");

      alert("Signup successful!");
      navigate("/login");
    } catch (err) {
      setError(err.message || "Signup failed. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const strengthColor = {
    "Too Weak": "#dc2626",
    Easy: "#ea580c",
    Medium: "#ca8a04",
    Strong: "#16a34a",
  };

  return (
    <div className="flex min-h-screen flex-col bg-slate-50">
      <Header />

      <main className="flex flex-1 items-center justify-center px-4 py-10">
        <div className="w-full max-w-md rounded-2xl border bg-white p-8 shadow">
          <h1 className="text-center text-2xl font-semibold">
            BMTC User Registration
          </h1>

          <p className="mt-2 text-center text-sm text-slate-500">
            Passenger / Conductor / Admin
          </p>

          {/* Role selection */}
          <div className="mt-4 flex justify-center gap-6 text-sm">
            {["passenger", "conductor", "admin"].map((item) => (
              <label key={item} className="flex items-center gap-2">
                <input
                  type="radio"
                  name="role"
                  value={item}
                  checked={role === item}
                  onChange={() => handleRoleChange(item)}
                />
                <span className="capitalize">{item}</span>
              </label>
            ))}
          </div>

          <form onSubmit={handleSubmit} className="mt-6 space-y-3">
            <input
              type="text"
              placeholder="Full Name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="input w-full"
              autoComplete="name"
              required
            />

            <input
              type="tel"
              placeholder="10-digit Phone Number"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              className="input w-full"
              inputMode="numeric"
              maxLength={10}
              autoComplete="tel-national"
              required
            />

            {(role === "conductor" || role === "admin") && (
              <input
                type="email"
                placeholder="Email Address"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="input w-full"
                autoComplete="email"
                required
              />
            )}

            {role === "conductor" && (
              <>
                <input
                  type="text"
                  placeholder="Badge ID"
                  value={badgeId}
                  onChange={(e) => setBadgeId(e.target.value)}
                  className="input w-full"
                  required
                />

                <input
                  type="text"
                  placeholder="Depot Number"
                  value={depot}
                  onChange={(e) => setDepot(e.target.value)}
                  className="input w-full"
                  required
                />
              </>
            )}

            <div>
              <input
                type="password"
                placeholder="Password"
                value={password}
                onChange={handlePasswordChange}
                className="input w-full"
                autoComplete="new-password"
                required
              />

              {password && (
                <p
                  className="mt-1 text-sm font-semibold"
                  style={{ color: strengthColor[strength] }}
                >
                  Password strength: {strength}
                </p>
              )}
            </div>

            <input
              type="password"
              placeholder="Confirm Password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              className="input w-full"
              autoComplete="new-password"
              required
            />

            <div>
              <input
                type="text"
                placeholder="Six-digit OTP"
                value={otp}
                onChange={(e) =>
                  setOtp(e.target.value.replace(/\D/g, "").slice(0, 6))
                }
                className="input w-full"
                inputMode="numeric"
                maxLength={6}
                autoComplete="one-time-code"
                required
              />

              <p className="mt-1 text-xs text-slate-500">
                In development mode, find the OTP in the Flask backend
                terminal on port 5000.
              </p>
            </div>

            <button
              type="button"
              onClick={handleRequestOtp}
              disabled={otpLoading || loading}
              className="w-full rounded bg-gray-600 py-2 font-semibold text-white hover:bg-gray-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {otpLoading ? "Generating OTP..." : "Request OTP"}
            </button>

            {error && (
              <p
                role="alert"
                className="rounded bg-red-50 p-3 text-sm text-red-700"
              >
                {error}
              </p>
            )}

            {success && (
              <p
                role="status"
                className="rounded bg-green-50 p-3 text-sm text-green-700"
              >
                {success}
              </p>
            )}

            <button
              type="submit"
              disabled={loading || otpLoading}
              className="w-full rounded bg-indigo-600 py-2 font-semibold text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {loading ? "Registering..." : "Create Account"}
            </button>
          </form>

          <p className="mt-4 text-center text-xs">
            Already registered?{" "}
            <Link to="/login" className="text-indigo-600 hover:underline">
              Login
            </Link>
          </p>
        </div>
      </main>

      <Footer />
    </div>
  );
}
