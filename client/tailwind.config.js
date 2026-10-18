/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,jsx,ts,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        headline: ["system-ui", "sans-serif"],
      },
      colors: {
        primary: "#4f46e5",
      },
    },
  },
  plugins: [],
};
