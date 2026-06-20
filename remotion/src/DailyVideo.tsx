import {
  AbsoluteFill,
  Audio,
  interpolate,
  Sequence,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { loadFont } from "@remotion/google-fonts/Inter";
import { Caption, VideoProps } from "./types";

const { fontFamily } = loadFont("normal", {
  weights: ["400", "600", "700", "800", "900"],
  subsets: ["latin"],
});

// ── Paleta de marca ──────────────────────────────────────────────────────────
const INK = "#211b17";
const GOLD = "#C4A574";
const CREAM = "#F8F6F2";
const WHITE = "#FFFFFF";

// Separador de millar manual (no depende de los datos de locale del headless)
const fmt = (n: number) => n.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ".");

// ── Fondo animado (degradado + halos a la deriva + viñeta) ─────────────────────
const Fondo: React.FC = () => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const t = frame / Math.max(1, durationInFrames);
  const gx = interpolate(Math.sin(frame / 90), [-1, 1], [-120, 120]);
  const gy = interpolate(Math.cos(frame / 110), [-1, 1], [-100, 100]);
  const sx = interpolate(Math.cos(frame / 100), [-1, 1], [120, -120]);
  const sy = interpolate(Math.sin(frame / 80), [-1, 1], [200, -60]);
  return (
    <AbsoluteFill
      style={{
        background: `linear-gradient(165deg, #16110e 0%, ${INK} 45%, #16110e 100%)`,
      }}
    >
      <div
        style={{
          position: "absolute",
          width: 900,
          height: 900,
          left: 90 + gx,
          top: 200 + gy,
          borderRadius: "50%",
          background: `radial-gradient(circle, rgba(196,165,116,0.22), rgba(196,165,116,0) 70%)`,
          filter: "blur(20px)",
        }}
      />
      <div
        style={{
          position: "absolute",
          width: 820,
          height: 820,
          right: -80 + sx,
          bottom: 220 + sy,
          borderRadius: "50%",
          background: `radial-gradient(circle, rgba(122,139,110,0.20), rgba(122,139,110,0) 70%)`,
          filter: "blur(20px)",
        }}
      />
      <AbsoluteFill
        style={{
          background:
            "radial-gradient(circle at 50% 42%, rgba(0,0,0,0) 45%, rgba(0,0,0,0.45) 100%)",
        }}
      />
      {/* leve barrido de luz que cruza con el tiempo */}
      <div
        style={{
          position: "absolute",
          top: 0,
          bottom: 0,
          width: 400,
          left: `${interpolate(t, [0, 1], [-30, 110])}%`,
          background:
            "linear-gradient(90deg, rgba(255,255,255,0) 0%, rgba(255,255,255,0.04) 50%, rgba(255,255,255,0) 100%)",
          transform: "skewX(-12deg)",
        }}
      />
    </AbsoluteFill>
  );
};

// ── Chrome persistente: logo, footer y barra de progreso ───────────────────────
const Chrome: React.FC = () => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const prog = interpolate(frame, [0, durationInFrames], [0, 100], {
    extrapolateRight: "clamp",
  });
  return (
    <AbsoluteFill style={{ fontFamily }}>
      <div style={{ position: "absolute", top: 96, width: "100%", textAlign: "center" }}>
        <div
          style={{
            color: CREAM,
            fontWeight: 900,
            fontSize: 52,
            letterSpacing: 8,
          }}
        >
          OPONOTICIAS
        </div>
        <div
          style={{
            width: 150,
            height: 6,
            background: GOLD,
            borderRadius: 3,
            margin: "18px auto 0",
          }}
        />
      </div>
      <div
        style={{
          position: "absolute",
          bottom: 120,
          width: "100%",
          textAlign: "center",
          color: GOLD,
          fontWeight: 700,
          fontSize: 40,
          letterSpacing: 1,
        }}
      >
        oponoticias.com
      </div>
      {/* barra de progreso */}
      <div style={{ position: "absolute", bottom: 0, width: "100%", height: 8, background: "rgba(255,255,255,0.08)" }}>
        <div style={{ width: `${prog}%`, height: "100%", background: GOLD }} />
      </div>
    </AbsoluteFill>
  );
};

// ── Utilidades de animación por escena ─────────────────────────────────────────
const useEntrada = (delay = 0) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame: frame - delay, fps, config: { damping: 16, mass: 0.7 } });
  return s;
};

const useSalida = (durInFrames: number, dur = 10) => {
  const frame = useCurrentFrame();
  return interpolate(frame, [durInFrames - dur, durInFrames], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
};

const centro: React.CSSProperties = {
  justifyContent: "center",
  alignItems: "center",
  textAlign: "center",
  fontFamily,
};

// ── Escena HOOK ────────────────────────────────────────────────────────────────
const EscenaHook: React.FC<{ c: Extract<Caption, { kind: "hook" }>; dur: number }> = ({
  c,
  dur,
}) => {
  const e1 = useEntrada(0);
  const e2 = useEntrada(8);
  const fade = useSalida(dur);
  return (
    <AbsoluteFill style={{ ...centro, opacity: fade }}>
      <div style={{ width: "86%" }}>
        <div
          style={{
            color: WHITE,
            fontWeight: 800,
            fontSize: 86,
            opacity: e1,
            transform: `translateY(${(1 - e1) * 40}px)`,
            textShadow: "0 6px 24px rgba(0,0,0,0.5)",
          }}
        >
          {c.titulo}
        </div>
        <div
          style={{
            color: GOLD,
            fontWeight: 900,
            fontSize: 104,
            marginTop: 16,
            opacity: e2,
            transform: `scale(${0.7 + e2 * 0.3})`,
            textShadow: "0 6px 28px rgba(0,0,0,0.55)",
          }}
        >
          {c.destacado}
        </div>
      </div>
    </AbsoluteFill>
  );
};

// ── Escena ITEM (tarjeta + contador de plazas) ─────────────────────────────────
const EscenaItem: React.FC<{ c: Extract<Caption, { kind: "item" }>; dur: number }> = ({
  c,
  dur,
}) => {
  const frame = useCurrentFrame();
  const card = useEntrada(0);
  const fade = useSalida(dur);
  const target = parseInt(c.plazas.replace(/\D/g, ""), 10);
  const tieneNum = !Number.isNaN(target);
  const valor = Math.round(
    interpolate(frame, [6, 26], [0, tieneNum ? target : 0], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    })
  );
  return (
    <AbsoluteFill style={{ ...centro, opacity: fade }}>
      <div
        style={{
          width: "84%",
          padding: "70px 50px",
          borderRadius: 44,
          background: "rgba(20,16,13,0.55)",
          border: "2px solid rgba(196,165,116,0.45)",
          boxShadow: "0 30px 80px rgba(0,0,0,0.45)",
          backdropFilter: "blur(4px)",
          opacity: card,
          transform: `translateY(${(1 - card) * 90}px) scale(${0.94 + card * 0.06})`,
        }}
      >
        <div style={{ fontSize: 96, lineHeight: 1, marginBottom: 6 }}>{c.icon}</div>
        <div style={{ color: GOLD, fontWeight: 900, fontSize: 130, lineHeight: 1.05 }}>
          {tieneNum ? fmt(valor) : c.plazas}
        </div>
        <div style={{ color: CREAM, fontWeight: 700, fontSize: 44, letterSpacing: 4, marginBottom: 26 }}>
          PLAZAS
        </div>
        <div style={{ color: WHITE, fontWeight: 800, fontSize: 60, lineHeight: 1.1 }}>
          {c.puesto}
        </div>
        <div style={{ color: GOLD, fontWeight: 600, fontSize: 48, marginTop: 12 }}>
          📍 {c.lugar}
        </div>
      </div>
    </AbsoluteFill>
  );
};

// ── Escena CTA ──────────────────────────────────────────────────────────────────
const EscenaCta: React.FC<{ c: Extract<Caption, { kind: "cta" }>; dur: number }> = ({
  c,
  dur,
}) => {
  const frame = useCurrentFrame();
  const e1 = useEntrada(0);
  const e2 = useEntrada(10);
  const fade = useSalida(dur);
  const pulse = 1 + 0.05 * Math.sin(frame / 6);
  return (
    <AbsoluteFill style={{ ...centro, opacity: fade }}>
      <div style={{ width: "86%" }}>
        <div
          style={{
            color: WHITE,
            fontWeight: 800,
            fontSize: 76,
            opacity: e1,
            transform: `translateY(${(1 - e1) * 40}px)`,
            lineHeight: 1.12,
          }}
        >
          {c.lineas.map((l, i) => (
            <div key={i}>{l}</div>
          ))}
        </div>
        <div
          style={{
            display: "inline-block",
            marginTop: 48,
            padding: "26px 70px",
            borderRadius: 100,
            background: GOLD,
            color: INK,
            fontWeight: 900,
            fontSize: 58,
            letterSpacing: 2,
            opacity: e2,
            transform: `scale(${(0.8 + e2 * 0.2) * pulse})`,
            boxShadow: "0 14px 40px rgba(196,165,116,0.4)",
          }}
        >
          ▶ SEGUIR
        </div>
      </div>
    </AbsoluteFill>
  );
};

// ── Composición principal ───────────────────────────────────────────────────────
export const DailyVideo: React.FC<VideoProps> = ({ fps, captions, audio }) => {
  return (
    <AbsoluteFill style={{ backgroundColor: INK }}>
      <Fondo />
      {audio ? <Audio src={staticFile(audio)} /> : null}
      {captions.map((c, i) => {
        const from = Math.round(c.start * fps);
        const dur = Math.max(1, Math.round((c.end - c.start) * fps));
        return (
          <Sequence key={i} from={from} durationInFrames={dur}>
            {c.kind === "hook" ? (
              <EscenaHook c={c} dur={dur} />
            ) : c.kind === "item" ? (
              <EscenaItem c={c} dur={dur} />
            ) : (
              <EscenaCta c={c} dur={dur} />
            )}
          </Sequence>
        );
      })}
      <Chrome />
    </AbsoluteFill>
  );
};
