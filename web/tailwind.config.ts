import type { Config } from "tailwindcss";

// As paletas "zinc" (superfícies e textos) e "violet"/"brand" (destaque) apontam para variáveis CSS
// definidas por tema e por modo (claro/escuro) em app/globals.css. Assim todas as telas seguem o tema.
const scale = (name: string, steps: number[]) =>
  Object.fromEntries(steps.map((s) => [s, `rgb(var(--${name}-${s}) / <alpha-value>)`]));

const steps = [50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950];

export default {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        zinc: scale("z", steps),
        violet: scale("a", steps),
        fuchsia: scale("a", steps),
        white: "rgb(var(--strong) / <alpha-value>)",
        danger: "rgb(var(--danger) / <alpha-value>)",
        // cores fixas para selos sobre o vídeo (não mudam com o tema)
        onvideo: "#F4F4F5",
        brand: {
          DEFAULT: "rgb(var(--a-500) / <alpha-value>)",
          dark: "rgb(var(--a-700) / <alpha-value>)",
        },
      },
      fontFamily: {
        sans: ['"Segoe UI Variable"', '"Segoe UI"', "Poppins", "system-ui", "sans-serif"],
        display: ["Poppins", '"Segoe UI"', "system-ui", "sans-serif"],
      },
      boxShadow: {
        glass: "var(--glass-shadow)",
        glow: "0 0 0 1px rgb(var(--a-400) / .5), 0 8px 30px -6px rgb(var(--a-500) / .55)",
      },
    },
  },
  plugins: [],
} satisfies Config;
