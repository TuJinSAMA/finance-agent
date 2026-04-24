export type ImpactLevel = 2 | 3;

export interface GeoEvent {
  id: number;
  source_name: string;
  source_url: string;
  title: string;
  summary: string;
  impact_level: ImpactLevel;
  categories: string | null;
  region: string | null;
  event_date: string;
  is_active: boolean;
}

export interface GeoEventListResponse {
  events: GeoEvent[];
  total: number;
  level3_count: number;
  level2_count: number;
  last_updated: string | null;
}