export type Caption =
  | {
      kind: "hook";
      start: number; // segundos
      end: number;
      titulo: string; // "HOY en el BOE"
      destacado: string; // "5 oposiciones nuevas"
    }
  | {
      kind: "item";
      start: number;
      end: number;
      plazas: string; // dígitos, p.ej. "200"
      puesto: string;
      lugar: string;
      icon: string; // emoji de categoría
    }
  | {
      kind: "cta";
      start: number;
      end: number;
      lineas: string[];
    };

export type VideoProps = {
  fps: number;
  total: number; // duración total en segundos
  fecha: string; // "20 junio"
  captions: Caption[];
  audio: string | null; // nombre del archivo en public/, p.ej. "audio.wav"
};

export const DEFAULT_PROPS: VideoProps = {
  fps: 30,
  total: 16,
  fecha: "20 junio",
  audio: null,
  captions: [
    { kind: "hook", start: 0, end: 4.5, titulo: "HOY en el BOE", destacado: "5 oposiciones nuevas" },
    {
      kind: "item",
      start: 4.5,
      end: 8,
      plazas: "200",
      puesto: "Enfermero/a",
      lugar: "Andalucía",
      icon: "🏥",
    },
    {
      kind: "item",
      start: 8,
      end: 11.5,
      plazas: "85",
      puesto: "Auxiliar Administrativo",
      lugar: "Madrid",
      icon: "🗂️",
    },
    { kind: "cta", start: 11.5, end: 16, lineas: ["Síguenos y no te", "pierdas ninguna"] },
  ],
};
