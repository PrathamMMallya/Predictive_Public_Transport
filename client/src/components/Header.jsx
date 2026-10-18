import { Link, NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import logo from "../assets/logo.png";

export default function Header() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  function handleLogout() {
    logout();
    navigate("/", { replace: true });
  }

  return (
    <header className="border-b bg-white/80 backdrop-blur z-20 sticky top-0">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">

        {/* Logo */}
        <Link to="/" className="flex items-center">
          <img
            src={logo}
            alt="eSkill logo"
            className="h-9 w-auto object-contain"
          />
        </Link>

        {/* Navigation Links */}
        <nav className="hidden md:flex items-center gap-8 text-sm font-medium text-slate-700">
          <NavLink
            to="/"
            className={({ isActive }) =>
              isActive ? "text-primary" : "hover:text-primary"
            }
          >
            Features
          </NavLink>



          {/* Dashboard link based on role */}
          {user && (
            <NavLink
              to={
                user.role === "conductor"
                  ? "/conductor/dashboard"
                  : user.role === "passenger"
                  ? "/passenger/dashboard" 
                  : "/admin/dashboard"
              }
              className={({ isActive }) =>
                isActive ? "text-primary" : "hover:text-primary"
              }
            >
              Dashboard
            </NavLink>
          )}
        </nav>

        {/* Authentication Buttons */}
        <div className="flex items-center gap-3">
          {!user ? (
            <>
              {/* Not Logged In → show login & signup */}
              <Link
                to="/login"
                className="text-sm font-medium text-slate-700 hover:text-primary"
              >
                Log in
              </Link>

              <Link
                to="/signup"
                className="rounded-full bg-primary px-4 py-2 text-sm font-semibold text-white shadow hover:bg-indigo-600"
              >
                Sign up
              </Link>
            </>
          ) : (
            <>
              {/* Logged In → show username + logout */}
              <span className="text-sm font-medium text-slate-700">
                Hi, {user.name || user.role}
              </span>

              <button
                onClick={handleLogout}
                className="rounded-full border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100"
              >
                Logout
              </button>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
