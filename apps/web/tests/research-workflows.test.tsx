import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ChatPage } from '../src/pages/ChatPage';
import { ClaimsPage } from '../src/pages/ClaimsPage';
import { TimelinePage } from '../src/pages/TimelinePage';
import { BriefPage } from '../src/pages/BriefPage';
import { NotesPage } from '../src/pages/NotesPage';
import { SettingsPage } from '../src/pages/SettingsPage';
import { json, renderRoute, source } from './helpers';

test('renders citation-backed answers and source navigation', async () => {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input);
    if (url.endsWith('/sources')) return json({ items: [source], total: 1, limit: 100, offset: 0 });
    if (url.endsWith('/conversations'))
      return json([
        {
          id: 'chat-1',
          project_id: 'project-1',
          title: 'Research conversation',
          selected_source_ids: [],
          created_at: '2032-01-01',
          updated_at: '2032-01-01',
          messages: [
            {
              id: 'message-1',
              role: 'assistant',
              content: 'Boardings increased [Source 1].',
              generated: true,
              warning: null,
              created_at: '2032-01-01',
              citations: [
                {
                  id: 'citation-1',
                  source_id: 'source-1',
                  source_chunk_id: 'chunk-1',
                  source_revision: 0,
                  marker: '[Source 1]',
                  excerpt: 'Boardings increased from 6,800 to 8,240.',
                  location: 'page 1',
                  source_title: 'Boarding report',
                },
              ],
            },
          ],
        },
      ]);
    return json({});
  });
  renderRoute(<ChatPage />, '/projects/project-1/chat');
  expect(await screen.findByText('Boardings increased [Source 1].')).toBeInTheDocument();
  const citation = screen.getByRole('link', { name: /Source 1.*Boarding report/i });
  expect(citation).toHaveAttribute('href', '/projects/project-1/sources/source-1?page=1');
});

test('creates claims and labels contradiction counts', async () => {
  const claim = {
    id: 'claim-1',
    project_id: 'project-1',
    text: 'Totals conflict',
    claim_type: 'factual',
    status: 'disputed',
    confidence: null,
    user_notes: null,
    created_at: '2032-01-01',
    updated_at: '2032-01-01',
    evidence: [
      {
        id: 'e-1',
        claim_id: 'claim-1',
        source_id: 'source-1',
        source_chunk_id: null,
        source_revision: 0,
        excerpt: '7,510, not 8,240',
        location: null,
        relationship_type: 'contradicts',
        confidence: null,
        origin: 'user',
        notes: null,
        created_at: '2032-01-01',
        source_title: 'Boarding report',
      },
    ],
  };
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) =>
    String(input).endsWith('/claims')
      ? json([claim])
      : json({ items: [source], total: 1, limit: 100, offset: 0 }),
  );
  renderRoute(<ClaimsPage />, '/projects/project-1/claims');
  expect(await screen.findByText('Totals conflict')).toBeInTheDocument();
  expect(screen.getByText('contradicts').parentElement).toHaveTextContent('1');
});

test('reviews a suggested timeline event', async () => {
  const event = {
    id: 'event-1',
    project_id: 'project-1',
    title: 'Tuning began',
    date_start: null,
    date_end: null,
    date_label: 'around late spring',
    date_precision: 'approximate',
    description: 'No exact day.',
    confidence: 0.6,
    origin: 'model_suggestion',
    review_status: 'suggested',
    sort_order: 0,
    created_at: '2032-01-01',
    updated_at: '2032-01-01',
    evidence: [
      {
        id: 'te-1',
        source_id: 'source-1',
        source_revision: 0,
        excerpt: 'around late spring',
        location: 'meeting note',
      },
    ],
  };
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    if (String(input).endsWith('/sources'))
      return json({ items: [source], total: 1, limit: 100, offset: 0 });
    return init?.method === 'PATCH' ? json({ ...event, review_status: 'accepted' }) : json([event]);
  });
  renderRoute(<TimelinePage />, '/projects/project-1/timeline');
  await userEvent.click(await screen.findByRole('button', { name: 'Accept' }));
  await waitFor(() =>
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/timeline/event-1'),
      expect.objectContaining({ method: 'PATCH' }),
    ),
  );
});

test('edits and saves one brief section without regenerating the document', async () => {
  const section = {
    id: 'section-1',
    section_type: 'executive_summary',
    title: 'Executive summary',
    content: 'Draft',
    ordinal: 0,
    origin: 'generated',
    user_edited: false,
    generation_warning: null,
    updated_at: '2032-01-01',
  };
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (_input, init) =>
    init?.method === 'PATCH'
      ? json({ ...section, content: 'Reviewed text', origin: 'user', user_edited: true })
      : json([
          {
            id: 'brief-1',
            project_id: 'project-1',
            title: 'Brief',
            status: 'draft',
            created_at: '2032-01-01',
            updated_at: '2032-01-01',
            sections: [section],
          },
        ]),
  );
  renderRoute(<BriefPage />, '/projects/project-1/brief');
  const editor = await screen.findByLabelText('Executive summary content');
  await userEvent.clear(editor);
  await userEvent.type(editor, 'Reviewed text');
  await userEvent.click(screen.getByRole('button', { name: 'Save' }));
  await waitFor(() =>
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/sections/section-1'),
      expect.objectContaining({
        method: 'PATCH',
        body: JSON.stringify({ content: 'Reviewed text' }),
      }),
    ),
  );
});

test('requires an explicit in-app confirmation before replacing a preserved brief edit', async () => {
  const section = {
    id: 'section-1',
    section_type: 'executive_summary',
    title: 'Executive summary',
    content: 'Reviewed, user-authored summary.',
    ordinal: 0,
    origin: 'user',
    user_edited: true,
    generation_warning: null,
    updated_at: '2032-01-01',
  };
  const brief = {
    id: 'brief-1',
    project_id: 'project-1',
    title: 'Brief',
    status: 'draft',
    created_at: '2032-01-01',
    updated_at: '2032-01-01',
    sections: [section],
  };
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (_input, init) =>
    init?.method === 'POST'
      ? json({
          ...section,
          content: 'Regenerated summary.',
          origin: 'generated',
          user_edited: false,
        })
      : json([brief]),
  );

  renderRoute(<BriefPage />, '/projects/project-1/brief');
  await userEvent.click(await screen.findByRole('button', { name: 'Generate section' }));
  expect(screen.getByRole('dialog', { name: 'Replace preserved user edit?' })).toBeInTheDocument();
  expect(fetchMock.mock.calls.some(([, init]) => init?.method === 'POST')).toBe(false);

  await userEvent.click(screen.getByRole('button', { name: 'Keep my edit' }));
  expect(
    screen.queryByRole('dialog', { name: 'Replace preserved user edit?' }),
  ).not.toBeInTheDocument();
  expect(fetchMock.mock.calls.some(([, init]) => init?.method === 'POST')).toBe(false);

  await userEvent.click(screen.getByRole('button', { name: 'Generate section' }));
  await userEvent.click(screen.getByRole('button', { name: 'Replace and regenerate' }));
  await waitFor(() =>
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/sections/section-1/generate'),
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ force_replace_user_edit: true }),
      }),
    ),
  );
});

test('creates a user note linked to project-scoped research records', async () => {
  const claim = {
    id: 'claim-1',
    project_id: 'project-1',
    text: 'Stored claim',
    claim_type: 'factual',
    status: 'proposed',
    confidence: null,
    user_notes: null,
    created_at: '2032-01-01',
    updated_at: '2032-01-01',
    evidence: [],
  };
  const event = {
    id: 'event-1',
    project_id: 'project-1',
    title: 'Stored event',
    date_start: null,
    date_end: null,
    date_label: null,
    date_precision: 'unknown',
    description: 'Event',
    confidence: null,
    origin: 'user',
    review_status: 'accepted',
    sort_order: 0,
    created_at: '2032-01-01',
    updated_at: '2032-01-01',
    evidence: [],
  };
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input);
    if (init?.method === 'POST')
      return json(
        {
          id: 'note-1',
          project_id: 'project-1',
          ...JSON.parse(String(init.body)),
          created_at: '2032-01-01',
          updated_at: '2032-01-01',
        },
        201,
      );
    if (url.endsWith('/sources')) return json({ items: [source], total: 1, limit: 100, offset: 0 });
    if (url.endsWith('/claims')) return json([claim]);
    if (url.endsWith('/timeline')) return json([event]);
    return json([]);
  });
  renderRoute(<NotesPage />, '/projects/project-1/notes');
  await userEvent.click(await screen.findByRole('button', { name: 'New note' }));
  await userEvent.type(screen.getByLabelText('Title'), 'Linked note');
  await userEvent.type(screen.getByLabelText('Note'), 'User interpretation');
  await userEvent.selectOptions(screen.getByLabelText('Link source'), 'source-1');
  await userEvent.selectOptions(screen.getByLabelText('Link claim'), 'claim-1');
  await userEvent.selectOptions(screen.getByLabelText('Link event'), 'event-1');
  await userEvent.click(screen.getByRole('button', { name: 'Save user note' }));
  await waitFor(() =>
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/notes'),
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          title: 'Linked note',
          content: 'User interpretation',
          source_id: 'source-1',
          claim_id: 'claim-1',
          timeline_event_id: 'event-1',
        }),
      }),
    ),
  );
});

test('downloads an explicit full-workspace backup from settings', async () => {
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
  const createObjectUrl = vi.fn(() => 'blob:backup');
  const revokeObjectUrl = vi.fn();
  class DownloadURL extends URL {
    static createObjectURL = createObjectUrl;
    static revokeObjectURL = revokeObjectUrl;
  }
  vi.stubGlobal('URL', DownloadURL);
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input);
    if (url.endsWith('/settings')) {
      return json({
        data_dir: '/local/citetrail',
        model_provider: 'ollama',
        model_name: 'local-model',
        model_base_url: 'http://127.0.0.1:11434',
        provider_requests_leave_device: false,
        model_api_key_configured: false,
        semantic_search_enabled: true,
        embedding_model: 'deterministic-feature-hash-v1',
        max_upload_bytes: 1000,
        max_download_bytes: 1000,
        request_timeout_seconds: 20,
        max_pdf_pages: 100,
        ocr_mode: 'disabled',
        ingestion_worker_mode: 'durable embedded single worker',
        ingestion_poll_seconds: 0.5,
        remote_provider_warning: 'Selected excerpts only.',
      });
    }
    if (url.endsWith('/health')) return json({ status: 'healthy' });
    if (url.endsWith('/maintenance/backups') && init?.method === 'POST') {
      return new Response(new Blob(['verified backup']), {
        headers: {
          'Content-Type': 'application/vnd.citetrail.backup+zip',
          'Content-Disposition': 'attachment; filename="citetrail-backup.ctbackup"',
        },
      });
    }
    return json({});
  });

  renderRoute(<SettingsPage />, '/projects/project-1/settings');
  await userEvent.click(await screen.findByRole('button', { name: 'Download workspace backup' }));

  await screen.findByText(/Backup created/);
  expect(fetchMock).toHaveBeenCalledWith(
    '/api/v1/maintenance/backups',
    expect.objectContaining({
      method: 'POST',
      headers: expect.objectContaining({ 'X-CiteTrail-Intent': 'backup' }),
    }),
  );
  expect(createObjectUrl).toHaveBeenCalledWith(expect.any(Blob));
  expect(click).toHaveBeenCalled();
  expect(revokeObjectUrl).toHaveBeenCalledWith('blob:backup');
});
