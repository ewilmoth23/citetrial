import type {
  Activity,
  Brief,
  BriefSection,
  Claim,
  Conversation,
  Evidence,
  Message,
  Note,
  Page,
  ProcessingJob,
  Project,
  SearchResult,
  Source,
  SourceContent,
  TimelineEvent,
} from '../types/api';

const API_ROOT = import.meta.env.VITE_API_URL ?? '/api/v1';

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details?: unknown,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (!(init?.body instanceof FormData)) headers.set('Content-Type', 'application/json');
  const response = await fetch(`${API_ROOT}${path}`, { ...init, headers });
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as {
      error?: { code?: string; message?: string; details?: unknown };
    };
    throw new ApiError(
      response.status,
      body.error?.code ?? 'request_failed',
      body.error?.message ?? `Request failed (${response.status})`,
      body.error?.details,
    );
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

async function requestDownload(
  path: string,
  init: RequestInit,
): Promise<{ blob: Blob; filename: string }> {
  const response = await fetch(`${API_ROOT}${path}`, init);
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as {
      error?: { code?: string; message?: string; details?: unknown };
    };
    throw new ApiError(
      response.status,
      body.error?.code ?? 'request_failed',
      body.error?.message ?? `Request failed (${response.status})`,
      body.error?.details,
    );
  }
  const disposition = response.headers.get('Content-Disposition') ?? '';
  const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
  const simple = disposition.match(/filename="?([^";]+)"?/i)?.[1];
  const filename = encoded ? decodeURIComponent(encoded) : simple || 'citetrail-workspace.ctbackup';
  return { blob: await response.blob(), filename };
}

export const api = {
  health: () => request<Record<string, unknown>>('/health'),
  listProjects: (includeArchived = false) =>
    request<Page<Project>>(`/projects?include_archived=${includeArchived}`),
  getProject: (id: string) => request<Project>(`/projects/${id}`),
  createProject: (body: { title: string; primary_question: string; description?: string }) =>
    request<Project>('/projects', { method: 'POST', body: JSON.stringify(body) }),
  updateProject: (id: string, body: Partial<Project>) =>
    request<Project>(`/projects/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  archiveProject: (id: string) => request<Project>(`/projects/${id}/archive`, { method: 'POST' }),
  reopenProject: (id: string) => request<Project>(`/projects/${id}/reopen`, { method: 'POST' }),
  deleteProject: (id: string) => request<void>(`/projects/${id}`, { method: 'DELETE' }),
  history: (id: string) => request<Activity[]>(`/projects/${id}/history`),
  listSources: (projectId: string) => request<Page<Source>>(`/projects/${projectId}/sources`),
  getSource: (projectId: string, sourceId: string) =>
    request<Source>(`/projects/${projectId}/sources/${sourceId}`),
  getSourceJobs: (projectId: string, sourceId: string) =>
    request<ProcessingJob[]>(`/projects/${projectId}/sources/${sourceId}/jobs`),
  getSourceContent: (projectId: string, sourceId: string) =>
    request<SourceContent>(`/projects/${projectId}/sources/${sourceId}/content`),
  addWebSource: (projectId: string, url: string) =>
    request<Source>(`/projects/${projectId}/sources/web`, {
      method: 'POST',
      body: JSON.stringify({ url }),
    }),
  uploadSource: (projectId: string, file: File) => {
    const data = new FormData();
    data.set('file', file);
    return request<Source>(`/projects/${projectId}/sources/upload`, { method: 'POST', body: data });
  },
  addNoteSource: (projectId: string, body: { title: string; content: string }) =>
    request<Source>(`/projects/${projectId}/sources/notes`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  updateSource: (projectId: string, sourceId: string, body: Record<string, unknown>) =>
    request<Source>(`/projects/${projectId}/sources/${sourceId}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  correctSource: (
    projectId: string,
    sourceId: string,
    correctedText: string,
    correctionNote: string,
  ) =>
    request<Source>(`/projects/${projectId}/sources/${sourceId}/correction`, {
      method: 'POST',
      body: JSON.stringify({ corrected_text: correctedText, correction_note: correctionNote }),
    }),
  retrySource: (projectId: string, sourceId: string) =>
    request<Source>(`/projects/${projectId}/sources/${sourceId}/retry`, { method: 'POST' }),
  deleteSource: (projectId: string, sourceId: string) =>
    request<void>(`/projects/${projectId}/sources/${sourceId}`, { method: 'DELETE' }),
  search: (projectId: string, body: Record<string, unknown>) =>
    request<{ query: string; results: SearchResult[]; warnings: string[] }>(
      `/projects/${projectId}/search`,
      { method: 'POST', body: JSON.stringify(body) },
    ),
  listClaims: (projectId: string) => request<Claim[]>(`/projects/${projectId}/claims`),
  createClaim: (projectId: string, body: Record<string, unknown>) =>
    request<Claim>(`/projects/${projectId}/claims`, { method: 'POST', body: JSON.stringify(body) }),
  updateClaim: (projectId: string, claimId: string, body: Record<string, unknown>) =>
    request<Claim>(`/projects/${projectId}/claims/${claimId}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  deleteClaim: (projectId: string, claimId: string) =>
    request<void>(`/projects/${projectId}/claims/${claimId}`, { method: 'DELETE' }),
  connectEvidence: (projectId: string, claimId: string, body: Record<string, unknown>) =>
    request<Evidence>(`/projects/${projectId}/claims/${claimId}/evidence`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  updateEvidence: (projectId: string, claimId: string, evidenceId: string, relationship: string) =>
    request<Evidence>(
      `/projects/${projectId}/claims/${claimId}/evidence/${evidenceId}?relationship_type=${relationship}`,
      { method: 'PATCH' },
    ),
  listTimeline: (projectId: string) => request<TimelineEvent[]>(`/projects/${projectId}/timeline`),
  createTimelineEvent: (projectId: string, body: Record<string, unknown>) =>
    request<TimelineEvent>(`/projects/${projectId}/timeline`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  updateTimelineEvent: (projectId: string, id: string, body: Record<string, unknown>) =>
    request<TimelineEvent>(`/projects/${projectId}/timeline/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  listNotes: (projectId: string, query = '') =>
    request<Note[]>(
      `/projects/${projectId}/notes${query ? `?query=${encodeURIComponent(query)}` : ''}`,
    ),
  createNote: (projectId: string, body: Record<string, unknown>) =>
    request<Note>(`/projects/${projectId}/notes`, { method: 'POST', body: JSON.stringify(body) }),
  updateNote: (projectId: string, noteId: string, body: Record<string, unknown>) =>
    request<Note>(`/projects/${projectId}/notes/${noteId}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  deleteNote: (projectId: string, noteId: string) =>
    request<void>(`/projects/${projectId}/notes/${noteId}`, { method: 'DELETE' }),
  listConversations: (projectId: string) =>
    request<Conversation[]>(`/projects/${projectId}/conversations`),
  createConversation: (projectId: string, selectedSourceIds: string[]) =>
    request<Conversation>(`/projects/${projectId}/conversations`, {
      method: 'POST',
      body: JSON.stringify({
        title: 'Research conversation',
        selected_source_ids: selectedSourceIds,
      }),
    }),
  askQuestion: (
    projectId: string,
    conversationId: string,
    question: string,
    selectedSourceIds: string[],
  ) =>
    request<{
      user_message: Message;
      answer_message: Message;
      retrieved: SearchResult[];
      provider_available: boolean;
    }>(`/projects/${projectId}/conversations/${conversationId}/messages`, {
      method: 'POST',
      body: JSON.stringify({
        question,
        selected_source_ids: selectedSourceIds,
        retrieval_mode: 'hybrid',
      }),
    }),
  listBriefs: (projectId: string) => request<Brief[]>(`/projects/${projectId}/briefs`),
  createBrief: (projectId: string) =>
    request<Brief>(`/projects/${projectId}/briefs`, {
      method: 'POST',
      body: JSON.stringify({ title: 'Research brief' }),
    }),
  updateBriefSection: (
    projectId: string,
    briefId: string,
    sectionId: string,
    body: Record<string, unknown>,
  ) =>
    request<BriefSection>(`/projects/${projectId}/briefs/${briefId}/sections/${sectionId}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  generateBriefSection: (projectId: string, briefId: string, sectionId: string, force = false) =>
    request<BriefSection>(
      `/projects/${projectId}/briefs/${briefId}/sections/${sectionId}/generate`,
      { method: 'POST', body: JSON.stringify({ force_replace_user_edit: force }) },
    ),
  getSettings: () => request<Record<string, unknown>>('/settings'),
  createWorkspaceBackup: () =>
    requestDownload('/maintenance/backups', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CiteTrail-Intent': 'backup',
      },
      body: '{}',
    }),
};

export const exportUrl = (projectId: string, format: 'markdown' | 'json', options = '') =>
  `${API_ROOT}/projects/${projectId}/exports/${format}${options}`;

export const sourceFileUrl = (projectId: string, sourceId: string) =>
  `${API_ROOT}/projects/${projectId}/sources/${sourceId}/file`;
