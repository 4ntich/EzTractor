import Link from "next/link";

const steps = [
  { n: "1", t: "Cole o link ou envie o vídeo", d: "VOD da Twitch, Kick, YouTube ou arquivo MP4/MKV." },
  { n: "2", t: "A IA encontra os melhores momentos", d: "Picos de áudio, trocas de cena, reações e fala." },
  { n: "3", t: "Receba clipes 9:16 prontos", d: "Com legenda animada, gancho e nota de potencial viral." },
];

export default function Home() {
  return (
    <main className="mx-auto max-w-5xl px-4 py-10 sm:px-6">
      <header className="flex items-center justify-between">
        <span className="text-xl font-black tracking-tight">
          Ez<span className="text-brand">Tractor</span>
        </span>
        <Link href="/login" className="btn-ghost">
          Entrar
        </Link>
      </header>

      <section className="py-20 text-center">
        <h1 className="text-4xl font-black leading-tight sm:text-6xl">
          Sua live de 4 horas vira <span className="text-brand">clipes virais</span> em minutos
        </h1>
        <p className="mx-auto mt-6 max-w-2xl text-lg text-zinc-400">
          O EzTractor assiste à gravação inteira, acha as jogadas e reações que prendem a atenção e entrega clipes
          verticais com legenda, prontos para postar.
        </p>
        <div className="mt-10 flex justify-center gap-3">
          <Link href="/login?mode=register" className="btn px-6 py-3 text-base">
            Começar grátis
          </Link>
          <Link href="/app" className="btn-ghost px-6 py-3 text-base">
            Ir para o painel
          </Link>
        </div>
        <p className="mt-3 text-xs text-zinc-500">120 créditos grátis no cadastro · 1 crédito = 1 minuto de vídeo</p>
      </section>

      <section className="grid gap-4 sm:grid-cols-3">
        {steps.map((s) => (
          <div key={s.n} className="card p-6">
            <div className="mb-3 flex h-8 w-8 items-center justify-center rounded-full bg-brand text-sm font-bold">
              {s.n}
            </div>
            <h3 className="font-semibold">{s.t}</h3>
            <p className="mt-1 text-sm text-zinc-400">{s.d}</p>
          </div>
        ))}
      </section>
    </main>
  );
}
