export type Caption =
  | {
      kind: "portada";
      start: number; // segundos
      end: number;
      titulo: string; // "El BOE de hoy"
      total: number; // nº de convocatorias del día
      fecha: string; // "28 de junio"
    }
  | {
      kind: "sector";
      start: number;
      end: number;
      titulo: string; // "Por sector"
      total: number;
      items: { label: string; count: number }[];
    }
  | {
      kind: "destacadas";
      start: number;
      end: number;
      titulo: string; // "Destacadas"
      items: { puesto: string; org: string; tag: string }[];
      extra?: number; // cuántas más hay en la web
    }
  | {
      kind: "newsletter";
      start: number;
      end: number;
      regalo: string; // "Calendario del Opositor 2026"
      cta: string; // "oponoticias.com"
    }
  | {
      kind: "cierre";
      start: number;
      end: number;
      lineas: string[]; // ["¿Buscas las de", "tu comunidad?"]
      cta: string; // "Fíltralas en oponoticias.com"
    };

export type VideoProps = {
  fps: number;
  total: number; // duración total en segundos
  fecha: string; // "28 junio"
  captions: Caption[];
  audio: string | null; // nombre del archivo en public/, p.ej. "audio.wav"
  seed?: number; // día del año → microvariación de fondo
};

export const DEFAULT_PROPS: VideoProps = {
  fps: 30,
  total: 21,
  fecha: "28 junio",
  audio: null,
  seed: 179,
  captions: [
    { kind: "portada", start: 0, end: 4, titulo: "El BOE de hoy", total: 47, fecha: "28 de junio" },
    {
      kind: "sector",
      start: 4,
      end: 8.5,
      titulo: "Por sector",
      total: 47,
      items: [
        { label: "Administración local", count: 28 },
        { label: "Sanidad", count: 6 },
        { label: "Justicia", count: 5 },
        { label: "Educación", count: 4 },
        { label: "Seguridad", count: 2 },
        { label: "Tecnología", count: 2 },
      ],
    },
    {
      kind: "destacadas",
      start: 8.5,
      end: 13,
      titulo: "Destacadas",
      items: [
        { puesto: "Auxiliar Administrativo", org: "Administración del Estado · Nacional", tag: "1.500 plazas" },
        { puesto: "Enfermero/a", org: "Servicio Andaluz de Salud · Andalucía", tag: "320 plazas" },
        { puesto: "Tramitación Procesal", org: "Ministerio de Justicia · Estatal", tag: "Estatal" },
      ],
      extra: 44,
    },
    {
      kind: "newsletter",
      start: 13,
      end: 17,
      regalo: "Calendario del Opositor 2026",
      cta: "oponoticias.com",
    },
    {
      kind: "cierre",
      start: 17,
      end: 21,
      lineas: ["¿Buscas las de", "tu comunidad?"],
      cta: "Fíltralas en oponoticias.com",
    },
  ],
};
