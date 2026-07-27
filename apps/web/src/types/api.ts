export type ProjectStatus = 'draft' | 'collecting_sources' | 'analyzing' | 'ready' | 'archived';

export interface Project {
  id: string;
  title: string;
  primary_question: string;
  description: string | null;
  status: ProjectStatus;
  created_at: string;
  updated_at: string;
  source_count: number;
  processed_source_count: number;
  claim_count: number;
  disputed_claim_count: number;
  unresolved_claim_count: number;
  timeline_event_count: number;
  brief_status: string | null;
}

export type SourceType = 'webpage' | 'pdf' | 'markdown' | 'text' | 'note';
export type ProcessingStatus =
  | 'queued'
  | 'retrieving'
  | 'uploaded'
  | 'extracting'
  | 'indexing'
  | 'ready'
  | 'ready_with_warnings'
  | 'failed';

export interface DuplicateWarning {
  id: string;
  related_source_id: string;
  duplicate_type: string;
  similarity: number;
  reason: string;
  confidence: number;
}

export interface ProcessingJob {
  id: string;
  source_id: string;
  status: 'queued' | 'running' | 'complete' | 'failed' | 'interrupted';
  stage: string;
  progress: number;
  attempt: number;
  recovery_count: number;
  error: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface Source {
  id: string;
  project_id: string;
  source_type: SourceType;
  original_name: string;
  normalized_url: string | null;
  final_url: string | null;
  title: string | null;
  author: string | null;
  publisher: string | null;
  publication_date: string | null;
  publication_date_is_explicit: boolean;
  retrieved_at: string | null;
  content_hash: string | null;
  extraction_method: string | null;
  processing_status: ProcessingStatus;
  warnings: string[];
  error_message: string | null;
  mime_type: string | null;
  http_status: number | null;
  redirect_count: number;
  category: string | null;
  importance: string | null;
  trust_note: string | null;
  source_label: string | null;
  created_at: string;
  updated_at: string;
  chunk_count: number;
  duplicate_warnings: DuplicateWarning[];
  processing_job: ProcessingJob | null;
}

export interface SourceContent {
  source_id: string;
  raw_text: string;
  normalized_text: string;
  corrected_text: string | null;
  correction_note: string | null;
  correction_revision: number;
  correction_history: Array<{
    id: string;
    revision: number;
    correction_note: string;
    previous_text_hash: string;
    corrected_text_hash: string;
    alignment_method: string;
    alignment_confidence: number;
    location_status: 'aligned' | 'reparsed' | 'unmapped';
    created_at: string;
  }>;
  page_count: number | null;
}

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface SourceLocation {
  page_number: number | null;
  heading_path: string | null;
  line_start: number | null;
  line_end: number | null;
}

export interface SearchResult {
  chunk_id: string;
  source_id: string;
  source_title: string;
  source_type: SourceType;
  location: SourceLocation;
  excerpt: string;
  score: number;
  method: string;
}

export interface Evidence {
  id: string;
  claim_id: string;
  source_id: string;
  source_chunk_id: string | null;
  excerpt: string;
  location: string | null;
  relationship_type: 'supports' | 'contradicts' | 'contextualizes' | 'uncertain';
  confidence: number | null;
  origin: string;
  source_revision: number;
  notes: string | null;
  created_at: string;
  source_title: string | null;
}

export interface Claim {
  id: string;
  project_id: string;
  text: string;
  claim_type: string;
  status: string;
  confidence: number | null;
  user_notes: string | null;
  created_at: string;
  updated_at: string;
  evidence: Evidence[];
}

export interface TimelineEvent {
  id: string;
  project_id: string;
  title: string;
  date_start: string | null;
  date_end: string | null;
  date_label: string | null;
  date_precision: 'exact_day' | 'month' | 'year' | 'approximate' | 'unknown';
  description: string;
  confidence: number | null;
  origin: string;
  review_status: string;
  sort_order: number;
  created_at: string;
  updated_at: string;
  evidence: Array<{
    id: string;
    source_id: string;
    source_revision: number;
    excerpt: string;
    location: string | null;
  }>;
}

export interface Note {
  id: string;
  project_id: string;
  title: string;
  content: string;
  source_id: string | null;
  claim_id: string | null;
  timeline_event_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface Citation {
  id: string;
  source_id: string;
  source_chunk_id: string;
  source_revision: number;
  marker: string;
  excerpt: string;
  location: string | null;
  source_title: string | null;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  generated: boolean;
  warning: string | null;
  created_at: string;
  citations: Citation[];
}

export interface Conversation {
  id: string;
  project_id: string;
  title: string;
  selected_source_ids: string[];
  created_at: string;
  updated_at: string;
  messages: Message[];
}

export interface BriefSection {
  id: string;
  section_type: string;
  title: string;
  content: string;
  ordinal: number;
  origin: string;
  user_edited: boolean;
  generation_warning: string | null;
  updated_at: string;
}

export interface Brief {
  id: string;
  project_id: string;
  title: string;
  status: string;
  created_at: string;
  updated_at: string;
  sections: BriefSection[];
}

export interface Activity {
  id: string;
  action: string;
  detail: string | null;
  created_at: string;
}

export interface ApiErrorBody {
  error?: { code?: string; message?: string; details?: unknown };
}
