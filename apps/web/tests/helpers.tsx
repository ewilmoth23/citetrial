import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render } from '@testing-library/react';
import type { ReactElement } from 'react';
import { MemoryRouter, Route, Routes, type RouteObject } from 'react-router-dom';

export function renderRoute(
  element: ReactElement,
  path = '/projects/project-1',
  extraRoutes: RouteObject[] = [],
) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return {
    ...render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            {extraRoutes.map((route) => (
              <Route key={route.path} path={route.path} element={route.element} />
            ))}
            <Route path="/projects/:projectId/*" element={element} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    ),
    client,
  };
}

export function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

export const project = {
  id: 'project-1',
  title: 'Harbor Loop research',
  primary_question: 'What changed?',
  description: null,
  status: 'analyzing',
  created_at: '2032-01-01T00:00:00Z',
  updated_at: '2032-01-01T00:00:00Z',
  source_count: 1,
  processed_source_count: 1,
  claim_count: 1,
  disputed_claim_count: 1,
  unresolved_claim_count: 0,
  timeline_event_count: 1,
  brief_status: 'draft',
};

export const source = {
  id: 'source-1',
  project_id: 'project-1',
  source_type: 'text',
  original_name: 'report.txt',
  normalized_url: null,
  final_url: null,
  title: 'Boarding report',
  author: null,
  publisher: null,
  publication_date: null,
  publication_date_is_explicit: false,
  retrieved_at: null,
  content_hash: 'abc',
  extraction_method: 'plain',
  processing_status: 'ready',
  warnings: [],
  error_message: null,
  mime_type: 'text/plain',
  http_status: null,
  redirect_count: 0,
  category: null,
  importance: null,
  trust_note: null,
  source_label: null,
  created_at: '2032-01-01T00:00:00Z',
  updated_at: '2032-01-01T00:00:00Z',
  chunk_count: 1,
  duplicate_warnings: [],
  processing_job: null,
};
