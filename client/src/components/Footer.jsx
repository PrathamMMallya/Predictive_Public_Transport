import { Link } from "react-router-dom";

export default function Footer() {
  return (
    <footer className="border-t bg-white">
      <div className="mx-auto max-w-6xl px-4 py-4">
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          {/* Left */}
          <p className="text-sm text-slate-500">Department of AIML</p>

          {/* Right */}
          <p className="text-sm text-slate-500 md:text-right">
            Developed by Nishta N Shetty &amp; Pratham M Mallya
          </p>
        </div>
      </div>
    </footer>
  );
}
