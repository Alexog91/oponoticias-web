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
import { loadFont } from "@remotion/google-fonts/PlayfairDisplay";
import { loadFont as loadSans } from "@remotion/google-fonts/Inter";
import { Caption, VideoProps } from "./types";

// Serif editorial para titulares; sans para datos/etiquetas.
const { fontFamily: serif } = loadFont("normal", { weights: ["500", "700", "800", "900"], subsets: ["latin"] });
const { fontFamily: sans } = loadSans("normal", { weights: ["400", "500", "600", "700", "800"], subsets: ["latin"] });

// ── Paleta editorial clara (marca: crema / tinta / dorado) ──────────────────────
const CREAM = "#F5EFE3"; // fondo página
const PAPER = "#FBF8F1"; // tarjetas
const INK = "#241d17"; // texto principal
const GOLD = "#C2A06A"; // acento (barras, reglas, pills)
const BRONZE = "#977536"; // dorado oscuro legible sobre crema (etiquetas)
const MUTED = "#8c8170"; // texto secundario
const LINE = "#e2dacb"; // hairline

// Microvariación de fondo por día (tonos crema), para que no sea idéntico.
const TONOS = ["#F5EFE3", "#F3EEE2", "#F6F0E6", "#F4EDDF", "#F5EEE0"];

const fmt = (n: number) => n.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ".");

// ── Fondo: crema plano + regla dorada superior + filigrana sutil ────────────────
const Fondo: React.FC<{ seed: number }> = ({ seed }) => {
  return (
    <AbsoluteFill style={{ backgroundColor: TONOS[seed % TONOS.length] }}>
      <div style={{ position: "absolute", top: 0, left: 0, right: 0, height: 10, background: GOLD }} />
      <div style={{ position: "absolute", bottom: 0, left: 0, right: 0, height: 10, background: GOLD }} />
    </AbsoluteFill>
  );
};

// ── Chrome persistente: cabecera de marca + barra de progreso ───────────────────
const Chrome: React.FC = () => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const prog = interpolate(frame, [0, durationInFrames], [0, 100], { extrapolateRight: "clamp" });
  return (
    <AbsoluteFill style={{ fontFamily: sans }}>
      <div style={{ position: "absolute", top: 70, width: "100%", textAlign: "center" }}>
        <div style={{ color: INK, fontWeight: 800, fontSize: 40, letterSpacing: 8 }}>OPONOTICIAS</div>
        <div style={{ width: 110, height: 4, background: GOLD, borderRadius: 2, margin: "14px auto 0" }} />
      </div>
      <div style={{ position: "absolute", bottom: 70, width: "100%", textAlign: "center", color: BRONZE, fontWeight: 600, fontSize: 34, letterSpacing: 1 }}>
        oponoticias.com
      </div>
      <div style={{ position: "absolute", bottom: 10, width: "100%", height: 6, background: "rgba(36,29,23,0.08)" }}>
        <div style={{ width: `${prog}%`, height: "100%", background: GOLD }} />
      </div>
    </AbsoluteFill>
  );
};

const centro: React.CSSProperties = {
  justifyContent: "center",
  alignItems: "center",
  textAlign: "center",
  fontFamily: sans,
};

// ── Transición: desliza cada escena (push) ──────────────────────────────────────
const Escena: React.FC<{ dur: number; dir: number; exit: number; children: React.ReactNode }> = ({
  dur,
  dir,
  exit,
  children,
}) => {
  const frame = useCurrentFrame();
  const { fps, width } = useVideoConfig();
  const s = spring({ frame, fps, config: { damping: 22, mass: 0.8 } });
  const enterX = (1 - s) * dir * width * 0.5;
  const out = interpolate(frame, [dur - exit, dur], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const exitX = out * -dir * width * 0.4;
  return (
    <AbsoluteFill style={{ ...centro, opacity: 1 - out, transform: `translateX(${enterX + exitX}px)` }}>
      {children}
    </AbsoluteFill>
  );
};

// Etiqueta de sección (kicker editorial)
const Kicker: React.FC<{ children: React.ReactNode; op?: number }> = ({ children, op = 1 }) => (
  <div style={{ color: BRONZE, fontWeight: 700, fontSize: 30, letterSpacing: 6, textTransform: "uppercase", opacity: op }}>
    {children}
  </div>
);

// ── PORTADA: el total del día ───────────────────────────────────────────────────
const EscenaPortada: React.FC<{ c: Extract<Caption, { kind: "portada" }> }> = ({ c }) => {
  const frame = useCurrentFrame();
  const e = spring({ frame, fps: 30, config: { damping: 16 } });
  const num = Math.round(interpolate(frame, [6, 30], [0, c.total], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }));
  return (
    <div style={{ width: "84%" }}>
      <div style={{ opacity: e, transform: `translateY(${(1 - e) * 20}px)` }}>
        <Kicker>{c.titulo}</Kicker>
        <div style={{ color: MUTED, fontFamily: serif, fontStyle: "italic", fontSize: 38, marginTop: 14 }}>{c.fecha}</div>
      </div>
      <div style={{ color: INK, fontFamily: serif, fontWeight: 900, fontSize: 280, lineHeight: 1, marginTop: 30 }}>
        {num}
      </div>
      <div style={{ color: INK, fontFamily: serif, fontSize: 56, marginTop: 4 }}>convocatorias nuevas</div>
      <div style={{ width: 90, height: 4, background: GOLD, margin: "44px auto 0" }} />
    </div>
  );
};

// ── POR SECTOR: barras con conteo (resumen de TODAS) ────────────────────────────
const EscenaSector: React.FC<{ c: Extract<Caption, { kind: "sector" }> }> = ({ c }) => {
  const frame = useCurrentFrame();
  const top = spring({ frame, fps: 30, config: { damping: 16 } });
  const max = Math.max(1, ...c.items.map((i) => i.count));
  return (
    <div style={{ width: "82%" }}>
      <div style={{ textAlign: "left", opacity: top }}>
        <Kicker>{c.titulo}</Kicker>
        <div style={{ color: MUTED, fontSize: 30, marginTop: 8 }}>de las {c.total} de hoy</div>
      </div>
      <div style={{ marginTop: 44, display: "flex", flexDirection: "column", gap: 30 }}>
        {c.items.map((it, i) => {
          const g = spring({ frame: frame - 8 - i * 4, fps: 30, config: { damping: 20 } });
          const w = (it.count / max) * 100 * g;
          return (
            <div key={i}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 10 }}>
                <div style={{ color: INK, fontWeight: 600, fontSize: 40 }}>{it.label}</div>
                <div style={{ color: BRONZE, fontWeight: 800, fontSize: 44 }}>{it.count}</div>
              </div>
              <div style={{ height: 18, background: "#e8e0d0", borderRadius: 9, overflow: "hidden" }}>
                <div style={{ width: `${w}%`, height: "100%", background: GOLD, borderRadius: 9 }} />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

// ── DESTACADAS: 2-3 tarjetas (las nacionales con etiqueta "Estatal") ────────────
const EscenaDestacadas: React.FC<{ c: Extract<Caption, { kind: "destacadas" }> }> = ({ c }) => {
  const frame = useCurrentFrame();
  const top = spring({ frame, fps: 30, config: { damping: 16 } });
  return (
    <div style={{ width: "84%" }}>
      <div style={{ textAlign: "left", opacity: top, marginBottom: 30 }}>
        <Kicker>{c.titulo}</Kicker>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 26 }}>
        {c.items.map((it, i) => {
          const e = spring({ frame: frame - 8 - i * 6, fps: 30, config: { damping: 20 } });
          return (
            <div
              key={i}
              style={{
                textAlign: "left",
                background: PAPER,
                border: `2px solid ${LINE}`,
                borderRadius: 24,
                padding: "34px 38px",
                opacity: e,
                transform: `translateX(${(1 - e) * 50}px)`,
              }}
            >
              <div style={{ color: INK, fontFamily: serif, fontWeight: 700, fontSize: 52, lineHeight: 1.05 }}>{it.puesto}</div>
              <div style={{ color: MUTED, fontSize: 32, marginTop: 10 }}>{it.org}</div>
              <div
                style={{
                  display: "inline-block",
                  marginTop: 20,
                  background: GOLD,
                  color: "#3a2c12",
                  fontWeight: 800,
                  fontSize: 32,
                  padding: "10px 26px",
                  borderRadius: 100,
                }}
              >
                {it.tag}
              </div>
            </div>
          );
        })}
      </div>
      {c.extra && c.extra > 0 ? (
        <div style={{ color: BRONZE, fontWeight: 700, fontSize: 38, marginTop: 30, opacity: top }}>
          + {c.extra} más en oponoticias.com
        </div>
      ) : null}
    </div>
  );
};

// ── NEWSLETTER: gancho con el lead magnet (Calendario del Opositor) ─────────────
const EscenaNewsletter: React.FC<{ c: Extract<Caption, { kind: "newsletter" }> }> = ({ c }) => {
  const frame = useCurrentFrame();
  const e1 = spring({ frame, fps: 30, config: { damping: 16 } });
  const e2 = spring({ frame: frame - 12, fps: 30, config: { damping: 14 } });
  const doc = spring({ frame: frame - 6, fps: 30, config: { damping: 12 } });
  return (
    <div style={{ width: "84%" }}>
      <div style={{ opacity: e1 }}>
        <Kicker>Gratis al suscribirte</Kicker>
      </div>
      {/* documento estilizado (la guía/calendario) */}
      <div
        style={{
          width: 300,
          height: 380,
          margin: "40px auto 0",
          background: PAPER,
          border: `3px solid ${INK}`,
          borderRadius: 14,
          transform: `rotate(-4deg) scale(${0.8 + doc * 0.2})`,
          opacity: doc,
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          alignItems: "center",
          boxShadow: `14px 14px 0 ${GOLD}`,
        }}
      >
        <div style={{ color: BRONZE, fontWeight: 700, fontSize: 26, letterSpacing: 4 }}>OPONOTICIAS</div>
        <div style={{ color: INK, fontFamily: serif, fontWeight: 900, fontSize: 120, lineHeight: 1 }}>2026</div>
        <div style={{ color: INK, fontWeight: 600, fontSize: 30 }}>Calendario</div>
        <div style={{ color: MUTED, fontSize: 26 }}>del Opositor</div>
      </div>
      <div style={{ color: INK, fontFamily: serif, fontWeight: 700, fontSize: 54, marginTop: 44, opacity: e2, lineHeight: 1.1 }}>
        Suscríbete y llévatelo
      </div>
      <div style={{ color: MUTED, fontSize: 36, marginTop: 14, opacity: e2 }}>+ las convocatorias en tu email</div>
    </div>
  );
};

// ── CIERRE: filtra por tu comunidad en la web + seguir ──────────────────────────
const EscenaCierre: React.FC<{ c: Extract<Caption, { kind: "cierre" }> }> = ({ c }) => {
  const frame = useCurrentFrame();
  const e1 = spring({ frame, fps: 30, config: { damping: 16 } });
  const e2 = spring({ frame: frame - 12, fps: 30, config: { damping: 14 } });
  const pulse = 1 + 0.04 * Math.sin(frame / 6);
  return (
    <div style={{ width: "86%" }}>
      <div style={{ color: INK, fontFamily: serif, fontWeight: 700, fontSize: 76, lineHeight: 1.1, opacity: e1 }}>
        {c.lineas.map((l, i) => (
          <div key={i}>{l}</div>
        ))}
      </div>
      <div
        style={{
          display: "inline-block",
          marginTop: 50,
          padding: "26px 64px",
          borderRadius: 100,
          background: GOLD,
          color: "#3a2c12",
          fontWeight: 800,
          fontSize: 44,
          opacity: e2,
          transform: `scale(${(0.85 + e2 * 0.15) * pulse})`,
        }}
      >
        {c.cta}
      </div>
    </div>
  );
};

// ── Composición principal ───────────────────────────────────────────────────────
const OVERLAP = 9;

export const DailyVideo: React.FC<VideoProps> = ({ fps, captions, audio, seed }) => {
  return (
    <AbsoluteFill style={{ backgroundColor: CREAM }}>
      <Fondo seed={seed ?? 0} />
      {audio ? <Audio src={staticFile(audio)} /> : null}
      {captions.map((c, i) => {
        const from = Math.round(c.start * fps);
        const base = Math.max(1, Math.round((c.end - c.start) * fps));
        const last = i === captions.length - 1;
        const dur = last ? base : base + OVERLAP;
        const exit = last ? 12 : OVERLAP;
        const dir = i % 2 === 0 ? 1 : -1;
        return (
          <Sequence key={i} from={from} durationInFrames={dur}>
            <Escena dur={dur} dir={dir} exit={exit}>
              {c.kind === "portada" ? (
                <EscenaPortada c={c} />
              ) : c.kind === "sector" ? (
                <EscenaSector c={c} />
              ) : c.kind === "destacadas" ? (
                <EscenaDestacadas c={c} />
              ) : c.kind === "newsletter" ? (
                <EscenaNewsletter c={c} />
              ) : (
                <EscenaCierre c={c} />
              )}
            </Escena>
          </Sequence>
        );
      })}
      <Chrome />
    </AbsoluteFill>
  );
};
