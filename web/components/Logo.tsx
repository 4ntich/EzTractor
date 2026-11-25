export default function Logo({ size = "md" }: { size?: "md" | "lg" }) {
  const box = size === "lg" ? "h-10 w-10 text-base" : "h-8 w-8 text-sm";
  return (
    <span className="flex items-center gap-2.5">
      <span className={`btn ${box} rounded-xl p-0 font-display font-black`} aria-hidden="true">Ez</span>
      <span className={`font-display font-extrabold tracking-tight text-white ${size === "lg" ? "text-2xl" : "text-lg"}`}>
        Ez<span className="text-gradient">Tractor</span>
      </span>
    </span>
  );
}
