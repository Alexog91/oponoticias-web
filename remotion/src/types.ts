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
      items: { puesto: string; org: string; tag: string; tema?: string }[];
      extra?: number; // cuántas más hay en la web
    }
  | {
      kind: "listado";
      start: number;
      end: number;
      titulo: string; // "Todas las de hoy"
      items: { puesto: string; lugar: string; tag: string; tema?: string }[];
      extra?: number; // cuántas más (no caben en el listado)
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
  total: 26.5,
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
        { label: "Administración", count: 30 },
        { label: "Sanidad", count: 6 },
        { label: "Justicia", count: 5 },
        { label: "Educación", count: 4 },
        { label: "Seguridad", count: 2 },
      ],
    },
    {
      kind: "destacadas",
      start: 8.5,
      end: 13,
      titulo: "Destacadas",
      items: [
        { puesto: "Auxiliar Administrativo", org: "Administración del Estado · Nacional", tag: "1.500 plazas", tema: "admin" },
        { puesto: "Enfermero/a", org: "Servicio Andaluz de Salud · Andalucía", tag: "320 plazas", tema: "sanidad" },
        { puesto: "Tramitación Procesal", org: "Ministerio de Justicia · Estatal", tag: "Estatal", tema: "justicia" },
      ],
      extra: 44,
    },
    {
      kind: "listado",
      start: 13,
      end: 18.5,
      titulo: "Todas las de hoy",
      items: [
        { puesto: "Auxiliar Administrativo", lugar: "Estatal", tag: "1.500 plazas", tema: "admin" },
        { puesto: "Enfermero/a", lugar: "Andalucía", tag: "320 plazas", tema: "sanidad" },
        { puesto: "Tramitación Procesal", lugar: "Estatal", tag: "", tema: "justicia" },
        { puesto: "Maestro de Primaria", lugar: "Galicia", tag: "30 plazas", tema: "educacion" },
        { puesto: "Policía Local", lugar: "C. Valenciana", tag: "40 plazas", tema: "seguridad" },
        { puesto: "Técnico Informático", lugar: "Madrid", tag: "12 plazas", tema: "tech" },
        { puesto: "Bombero", lugar: "Cataluña", tag: "8 plazas", tema: "seguridad" },
        { puesto: "Auxiliar de Biblioteca", lugar: "Castilla y León", tag: "", tema: "general" },
      ],
      extra: 39,
    },
    {
      kind: "newsletter",
      start: 18.5,
      end: 22.5,
      regalo: "Calendario del Opositor 2026",
      cta: "oponoticias.com",
    },
    {
      kind: "cierre",
      start: 22.5,
      end: 26.5,
      lineas: ["¿Buscas las de", "tu comunidad?"],
      cta: "Fíltralas en oponoticias.com",
    },
  ],
};
