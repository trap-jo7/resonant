import type { Config } from "tailwindcss";
export default {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: { bg: "#0D0F12", panel: "#171A1F", raised: "#20252C", ink: "#F3F4F6", dim: "#A6ADB8", accent: "#8BE0C1" },
      borderRadius: { md: "10px", lg: "12px", xl: "14px", "2xl": "18px" },
      fontFamily: { sans: ["Inter", "system-ui", "sans-serif"] },
    },
  },
  plugins: [],
} satisfies Config;
