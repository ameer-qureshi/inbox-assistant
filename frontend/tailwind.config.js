/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        desk: "#EDF0F3",      // sorting-office grey background
        sheet: "#FFFFFF",     // paper surfaces
        line: "#D5DBE3",      // dividers
        ink: { DEFAULT: "#15233B", soft: "#4A5872", faint: "#7D889B" },
        post: { DEFAULT: "#2347C5", dark: "#1A3698", tint: "#E6ECFB" },
        p1: { DEFAULT: "#B8322A", tint: "#FBE9E7" },
        p2: { DEFAULT: "#A86A12", tint: "#FBF1E1" },
        p3: { DEFAULT: "#6A7890", tint: "#EEF1F5" },
        ok: { DEFAULT: "#1F7A4D", tint: "#E3F4EA" },
      },
      fontFamily: {
        sans: ['"Public Sans"', "system-ui", "sans-serif"],
        read: ['"Literata"', "Georgia", "serif"],
      },
    },
  },
  plugins: [],
};
