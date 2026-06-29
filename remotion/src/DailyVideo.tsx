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

// ── Fondo: crema + halos dorados a la deriva + grano sutil (editorial) ──────────
// El crema plano se veía monótono entre días. Sin recurrir a B-roll de stock (que
// rompería el estilo editorial), se añade movimiento sutil: dos halos dorados que
// derivan lentamente y una capa de grano fina. Mantiene la marca, evita la monotonía.
const Fondo: React.FC<{ seed: number }> = ({ seed }) => {
  const frame = useCurrentFrame();
  const vaiven = (a: number, b: number, periodo: number, fase = 0) =>
    interpolate(Math.sin(frame / periodo + fase), [-1, 1], [a, b]);
  return (
    <AbsoluteFill style={{ backgroundColor: TONOS[seed % TONOS.length], overflow: "hidden" }}>
      <div
        style={{
          position: "absolute", width: 900, height: 900, borderRadius: "50%",
          background: `radial-gradient(circle, ${GOLD}26, transparent 70%)`,
          top: vaiven(-320, -180, 95), left: vaiven(-280, -150, 115),
        }}
      />
      <div
        style={{
          position: "absolute", width: 760, height: 760, borderRadius: "50%",
          background: `radial-gradient(circle, ${BRONZE}1f, transparent 70%)`,
          bottom: vaiven(-280, -150, 105, 1.2), right: vaiven(-260, -140, 125, 0.6),
        }}
      />
      {/* grano fino para dar textura de papel */}
      <svg style={{ position: "absolute", inset: 0, width: "100%", height: "100%", opacity: 0.05, mixBlendMode: "multiply" }}>
        <filter id="grano">
          <feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" stitchTiles="stitch" />
        </filter>
        <rect width="100%" height="100%" filter="url(#grano)" />
      </svg>
      <div style={{ position: "absolute", top: 0, left: 0, right: 0, height: 10, background: GOLD }} />
      <div style={{ position: "absolute", bottom: 0, left: 0, right: 0, height: 10, background: GOLD }} />
    </AbsoluteFill>
  );
};

// ── Iconos de categoría (Lucide, MIT) — trazos sobre crema ──────────────────────
const ICONOS: Record<string, string[]> = {
  sanidad: [
    "M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z",
    "M3.22 12H9.5l.5-1 2 4.5 2-7 1.5 3.5h5.27",
  ],
  educacion: [
    "M21.42 10.92a1 1 0 0 0-.02-1.83L12.83 5.18a2 2 0 0 0-1.66 0L2.6 9.08a1 1 0 0 0 0 1.83l8.57 3.91a2 2 0 0 0 1.66 0z",
    "M22 10v6",
    "M6 12.5V16a6 3 0 0 0 12 0v-3.5",
  ],
  seguridad: [
    "M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z",
  ],
  justicia: [
    "m16 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z",
    "m2 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z",
    "M7 21h10",
    "M12 3v18",
    "M3 7h2c2 0 5-1 7-2 2 1 5 2 7 2h2",
  ],
  tech: ["m16 18 6-6-6-6", "m8 6-6 6 6 6"],
  ciencia: [
    "M14 2v6a2 2 0 0 0 .24.96l5.51 10.08A2 2 0 0 1 18 22H6a2 2 0 0 1-1.76-2.96l5.51-10.08A2 2 0 0 0 10 8V2",
    "M6.45 15h11.1",
    "M8.5 2h7",
  ],
  admin: [
    "M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z",
  ],
  general: [
    "M10 18v-7",
    "M11.12 2.2a2 2 0 0 1 1.76.01l7.87 3.84c.48.24.31.95-.22.95H3.47c-.53 0-.7-.72-.22-.95z",
    "M14 18v-7",
    "M18 18v-7",
    "M3 22h18",
    "M6 18v-7",
  ],
};

const Icono: React.FC<{ tema?: string; size?: number; color?: string }> = ({ tema, size = 44, color = BRONZE }) => {
  const paths = ICONOS[tema ?? "general"] ?? ICONOS.general;
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      {paths.map((d, i) => (
        <path key={i} d={d} />
      ))}
    </svg>
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
                display: "flex",
                gap: 26,
                alignItems: "flex-start",
                textAlign: "left",
                background: PAPER,
                border: `2px solid ${LINE}`,
                borderRadius: 24,
                padding: "32px 36px",
                opacity: e,
                transform: `translateX(${(1 - e) * 50}px)`,
              }}
            >
              <div
                style={{
                  flex: "0 0 auto",
                  width: 88,
                  height: 88,
                  borderRadius: 22,
                  background: CREAM,
                  border: `2px solid ${LINE}`,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                <Icono tema={it.tema} size={48} />
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ color: INK, fontFamily: serif, fontWeight: 700, fontSize: 50, lineHeight: 1.05 }}>{it.puesto}</div>
                <div style={{ color: MUTED, fontSize: 32, marginTop: 8 }}>{it.org}</div>
                <div
                  style={{
                    display: "inline-block",
                    marginTop: 18,
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

// ── LISTADO: todas las del día (resumen tipo WhatsApp, con auto-scroll) ─────────
const EscenaListado: React.FC<{ c: Extract<Caption, { kind: "listado" }>; dur: number }> = ({ c, dur }) => {
  const frame = useCurrentFrame();
  const top = spring({ frame, fps: 30, config: { damping: 16 } });
  const ROW = 112; // alto aprox. por fila (incl. gap)
  const VIEW = 1180; // alto visible de la lista
  const extraRow = c.extra && c.extra > 0 ? 90 : 0;
  const contentH = c.items.length * ROW + extraRow;
  const maxScroll = Math.max(0, contentH - VIEW);
  // Desplaza el contenido durante la parte central de la escena (deja respiro
  // de entrada/salida). Si todo cabe (maxScroll=0), queda estático.
  const p = interpolate(frame, [14, dur - 14], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const y = -maxScroll * p;
  const fade = "linear-gradient(to bottom, transparent, #000 7%, #000 93%, transparent)";
  return (
    <div style={{ width: "88%" }}>
      <div style={{ textAlign: "left", opacity: top, marginBottom: 22 }}>
        <Kicker>{c.titulo}</Kicker>
        <div style={{ color: MUTED, fontSize: 30, marginTop: 8 }}>
          {c.items.length}
          {c.extra && c.extra > 0 ? `+` : ``} convocatorias de empleo público
        </div>
      </div>
      <div
        style={{
          height: VIEW,
          overflow: "hidden",
          maskImage: maxScroll > 0 ? fade : undefined,
          WebkitMaskImage: maxScroll > 0 ? fade : undefined,
        }}
      >
        <div style={{ transform: `translateY(${y}px)`, display: "flex", flexDirection: "column", gap: 16 }}>
          {c.items.map((it, i) => (
            <div
              key={i}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 20,
                background: PAPER,
                border: `2px solid ${LINE}`,
                borderRadius: 18,
                padding: "18px 24px",
                textAlign: "left",
              }}
            >
              <Icono tema={it.tema} size={36} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ color: INK, fontWeight: 600, fontSize: 38, lineHeight: 1.1, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                  {it.puesto}
                </div>
                <div style={{ color: MUTED, fontSize: 27 }}>{it.lugar}</div>
              </div>
              {it.tag ? (
                <div style={{ color: BRONZE, fontWeight: 800, fontSize: 30, whiteSpace: "nowrap" }}>{it.tag}</div>
              ) : null}
            </div>
          ))}
          {c.extra && c.extra > 0 ? (
            <div style={{ color: BRONZE, fontWeight: 700, fontSize: 34, textAlign: "center", padding: "14px 0" }}>
              + {c.extra} más en oponoticias.com
            </div>
          ) : null}
        </div>
      </div>
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
              ) : c.kind === "listado" ? (
                <EscenaListado c={c} dur={dur} />
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
