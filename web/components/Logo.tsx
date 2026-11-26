export default function Logo({ size = "md" }: { size?: "md" | "lg" }) {
  const box = size === "lg" ? "h-11 w-11" : "h-9 w-9";
  return (
    <span className="flex items-center gap-2.5">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src="/logo.png" alt="Garimpo Mestre" className={`${box} object-contain drop-shadow-[0_2px_6px_rgba(0,0,0,.5)]`} />
      <span className={`font-display font-extrabold tracking-tight text-white ${size === "lg" ? "text-2xl" : "hidden text-lg sm:inline"}`}>
        Ez<span className="text-gradient">Tractor</span>
      </span>
    </span>
  );
}
