import { Link, useNavigate } from "react-router-dom";
import { ArrowRight, Bus, Bot, Users, TrendingUp, Volume2, VolumeX } from "lucide-react";
import { useRef, useState } from "react";

import Header from "../components/Header";
import Footer from "../components/Footer";
import { useAuth } from "../context/AuthContext";

// ✅ Import music properly
import backgroundMusic from "../data/music.mpeg";

const featureCards = [
  {
    icon: Bot,
    title: "Smart Ticketing System",
    description:
      "Digitized ticket issuance and validation using secure, role-based access for BMTC operations.",
  },
  {
    icon: Users,
    title: "Passenger & Conductor Roles",
    description:
      "Separate dashboards for passengers and conductors ensure smooth and controlled ticket flow.",
  },
  {
    icon: TrendingUp,
    title: "Passenger OverCrowding Index",
    description:
      "Estimates overcrowding levels on buses in real-time and provides actionable insights for transport officers.",
  },
];

export default function Home() {
  const navigate = useNavigate();
  const { user } = useAuth();

  // ✅ MUSIC STATE + REF
  const audioRef = useRef(null);
  const [musicOn, setMusicOn] = useState(false);

  function toggleMusic() {
    if (!audioRef.current) return;

    if (musicOn) {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
    } else {
      audioRef.current.play();
    }

    setMusicOn(!musicOn);
  }

  function handleBookTicket() {
    if (!user) return navigate("/login");
    navigate(user.role === "passenger" ? "/passenger/dashboard" : "/conductor/dashboard");
  }

  function handleIssueTicket() {
    if (!user) return navigate("/login");
    navigate(user.role === "conductor" ? "/conductor/dashboard" : "/passenger/dashboard");
  }

  return (
    <div className="flex min-h-screen flex-col relative">
      <Header />

      {/* 🔊 Hidden Audio Element */}
      <audio ref={audioRef} src={backgroundMusic} loop />

      {/* HERO SECTION WITH VIDEO */}
      <section className="relative w-full h-screen overflow-hidden">
        <iframe
          className="absolute top-0 left-0 w-full h-[133%] object-cover -z-10"
          src="https://www.youtube.com/embed/wWBS652SMTA?autoplay=1&mute=1&loop=1&playlist=wWBS652SMTA&start=43&controls=0&modestbranding=1"
          title="BMTC Background"
          frameBorder="0"
          allow="autoplay; fullscreen"
          style={{ objectFit: "cover", width: "100%", height: "100%" }}
        ></iframe>

        <div className="absolute inset-0 bg-black/40 -z-10" />

        {/* HERO CONTENT */}
        <div className="relative flex flex-col items-center justify-start h-full text-center px-4 pt-16 md:pt-24 lg:pt-32">
          <h1 className="text-4xl font-bold sm:text-5xl md:text-6xl text-white">
            BMTC Overcrowding Monitoring System
          </h1>

          <p className="mt-4 text-lg text-white max-w-2xl">
            A digital platform for passengers, conductors, and administrators to manage overcrowding in
            BMTC efficiently and securely.
          </p>

          {/* 🔊 MUSIC TOGGLE BUTTON */}
          <button
            onClick={toggleMusic}
            className="mt-6 inline-flex items-center gap-2 rounded-full bg-white/90 px-5 py-2 
                       text-sm font-semibold text-slate-800 shadow hover:bg-white"
          >
            {musicOn ? (
              <>
                <VolumeX className="h-4 w-4" /> Music OFF
              </>
            ) : (
              <>
                <Volume2 className="h-4 w-4" /> Music ON
              </>
            )}
          </button>

          <div className="mt-8 flex flex-col gap-4 sm:flex-row sm:justify-center">
            <button
              onClick={handleBookTicket}
              className="inline-flex items-center justify-center rounded-full bg-primary px-6 py-3 
                         text-sm font-semibold text-white shadow hover:bg-indigo-600"
            >
              Book / View Tickets
              <ArrowRight className="ml-2 h-4 w-4" />
            </button>

            <button
              onClick={handleIssueTicket}
              className="inline-flex items-center justify-center rounded-full border border-slate-300 
                         bg-white px-6 py-3 text-sm font-semibold text-slate-800 shadow-sm hover:bg-slate-50"
            >
              Conductor Login
            </button>
          </div>
        </div>
      </section>

      {/* FEATURES SECTION */}
      <section className="w-full bg-gray-100 py-16">
        <div className="mx-auto max-w-6xl px-4">
          <h2 className="text-center text-3xl font-bold mb-12">
            Why BMTC Digital Ticketing?
          </h2>

          <div className="grid gap-8 md:grid-cols-3">
            {featureCards.map((feature) => {
              const Icon = feature.icon;
              return (
                <div
                  key={feature.title}
                  className="rounded-2xl border bg-white p-8 shadow-sm hover:shadow-lg"
                >
                  <div className="mb-4 flex justify-center">
                    <div className="rounded-full bg-primary/10 p-4">
                      <Icon className="h-8 w-8 text-primary" />
                    </div>
                  </div>

                  <h3 className="text-center text-lg font-semibold">
                    {feature.title}
                  </h3>

                  <p className="mt-2 text-center text-sm text-slate-600">
                    {feature.description}
                  </p>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="py-12 text-center">
        <Link
          to="/login"
          className="inline-flex items-center rounded-full bg-indigo-600 px-6 py-3 
                     text-sm font-semibold text-white hover:bg-indigo-700"
        >
          Login to BMTC System
          <Bus className="ml-2 h-4 w-4" />
        </Link>
      </section>

      <Footer />
    </div>
  );
}
