/**
 * SYNTHETIC development data (NFR-11). Parish names are real Libertador
 * parishes (public administrative geography); every sector, alias, meeting
 * point, provider, and number is invented. Never replace with real data.
 */
import type { AreaRef, MeetingPoint, NeedCategory } from '../schema';

export const TENANT = { id: 'tenant-csl', name: 'Ciudadanía Sin Límites', k: 5 } as const;

export const MY_PROVIDER = { id: 'prov-agua', name: 'Agua Solidaria (sintético)' };
export const OTHER_PROVIDERS = [
  { id: 'prov-carga', name: 'Red de Carga Comunitaria (sintético)' },
  { id: 'prov-fund', name: 'Fundación Ejemplo (sintético)' },
];

interface SectorSeed {
  id: string;
  name: string;
  aliases: string[];
  /** Need intensity per category, 0 = no reports at all (unknown). */
  intensity: Record<NeedCategory, number>;
  external: 'agrees' | 'conflicts' | 'none';
}

interface ParishSeed {
  id: string;
  name: string;
  sectors: SectorSeed[];
}

const PARISHES: ParishSeed[] = [
  {
    id: 'par-sucre',
    name: 'Sucre',
    sectors: [
      { id: 'sec-acacias', name: 'Las Acacias', aliases: ['Acacias de arriba'], intensity: { water_drinking: 9, water_other: 4, charging: 7 }, external: 'agrees' },
      { id: 'sec-mirador', name: 'El Mirador', aliases: ['Mirador Alto'], intensity: { water_drinking: 6, water_other: 0, charging: 8 }, external: 'none' },
      { id: 'sec-samanes', name: 'Los Samanes', aliases: [], intensity: { water_drinking: 1, water_other: 2, charging: 0 }, external: 'none' },
    ],
  },
  {
    id: 'par-23enero',
    name: '23 de Enero',
    sectors: [
      { id: 'sec-quebradita', name: 'La Quebradita', aliases: ['Quebradita', 'La Q'], intensity: { water_drinking: 10, water_other: 7, charging: 3 }, external: 'agrees' },
      { id: 'sec-bloque4', name: 'Bloque 4', aliases: ['Bloque Cuatro'], intensity: { water_drinking: 0, water_other: 0, charging: 0 }, external: 'none' },
      { id: 'sec-brisas', name: 'Las Brisas', aliases: [], intensity: { water_drinking: 5, water_other: 3, charging: 6 }, external: 'conflicts' },
    ],
  },
  {
    id: 'par-elvalle',
    name: 'El Valle',
    sectors: [
      { id: 'sec-carmen', name: 'El Carmen Alto', aliases: ['Carmen Alto'], intensity: { water_drinking: 2, water_other: 1, charging: 9 }, external: 'agrees' },
      { id: 'sec-cedros', name: 'Los Cedros', aliases: [], intensity: { water_drinking: 7, water_other: 5, charging: 2 }, external: 'none' },
    ],
  },
  {
    id: 'par-sanagustin',
    name: 'San Agustín',
    sectors: [
      { id: 'sec-esperanza', name: 'La Esperanza', aliases: ['Esperanza Norte'], intensity: { water_drinking: 8, water_other: 0, charging: 5 }, external: 'none' },
      { id: 'sec-vista', name: 'Vista Hermosa', aliases: [], intensity: { water_drinking: 3, water_other: 6, charging: 1 }, external: 'none' },
    ],
  },
];

export const PARISH_AREAS: AreaRef[] = PARISHES.map((p) => ({
  id: p.id,
  name: p.name,
  level: 'parish',
  parent_id: null,
  parent_name: 'Libertador',
  aliases: [],
}));

export const SECTOR_AREAS: AreaRef[] = PARISHES.flatMap((p) =>
  p.sectors.map((s) => ({
    id: s.id,
    name: s.name,
    level: 'sector' as const,
    parent_id: p.id,
    parent_name: p.name,
    aliases: s.aliases,
  })),
);

export const SECTOR_SEEDS: SectorSeed[] = PARISHES.flatMap((p) => p.sectors);

export const MEETING_POINTS: MeetingPoint[] = [
  { id: 'mp-acacias-plaza', sector_id: 'sec-acacias', name: 'Plaza Las Acacias', kind: 'plaza' },
  { id: 'mp-acacias-iglesia', sector_id: 'sec-acacias', name: 'Capilla San José (sintética)', kind: 'church' },
  { id: 'mp-mirador-escuela', sector_id: 'sec-mirador', name: 'Escuela El Mirador', kind: 'school' },
  { id: 'mp-quebradita-cancha', sector_id: 'sec-quebradita', name: 'Cancha de La Quebradita', kind: 'other' },
  { id: 'mp-brisas-bodega', sector_id: 'sec-brisas', name: 'Bodega La Esquina', kind: 'shop' },
  { id: 'mp-carmen-plaza', sector_id: 'sec-carmen', name: 'Plaza El Carmen', kind: 'plaza' },
  { id: 'mp-cedros-escuela', sector_id: 'sec-cedros', name: 'Escuela Los Cedros', kind: 'school' },
  { id: 'mp-esperanza-plaza', sector_id: 'sec-esperanza', name: 'Plaza La Esperanza', kind: 'plaza' },
];
