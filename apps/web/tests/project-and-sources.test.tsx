import { fireEvent, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { NewProjectPage } from '../src/pages/NewProjectPage';
import { SourceDetailPage } from '../src/pages/SourceDetailPage';
import { SourcesPage } from '../src/pages/SourcesPage';
import { json, renderRoute, source } from './helpers';

vi.mock('react-pdf', () => ({
  Document: () => null,
  Page: () => null,
  pdfjs: { GlobalWorkerOptions: {} },
}));

test('creates a project from the focused-question form', async () => {
  const fetchMock = vi
    .spyOn(globalThis, 'fetch')
    .mockResolvedValue(
      json(
        { ...source, id: 'project-1', title: 'Transit', primary_question: 'What changed?' },
        201,
      ),
    );
  renderRoute(<NewProjectPage />, '/projects/new', [
    { path: '/projects/new', element: <NewProjectPage /> },
    { path: '/projects/:projectId', element: <p>Project opened</p> },
  ]);
  await userEvent.type(screen.getByLabelText('Project title'), 'Transit');
  await userEvent.type(screen.getByLabelText('Primary research question'), 'What changed?');
  await userEvent.click(screen.getByRole('button', { name: /create project/i }));
  await screen.findByText('Project opened');
  expect(fetchMock).toHaveBeenCalledWith(
    '/api/v1/projects',
    expect.objectContaining({ method: 'POST' }),
  );
});

test('submits an https webpage and exposes processing states', async () => {
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input);
    if (url.endsWith('/sources') && !init?.method)
      return json({
        items: [
          {
            ...source,
            processing_status: 'indexing',
            processing_job: {
              id: 'job-1',
              source_id: 'source-1',
              status: 'running',
              stage: 'indexing',
              progress: 0.65,
              attempt: 1,
              recovery_count: 1,
              error: null,
              created_at: '2032-01-01T00:00:00Z',
              started_at: '2032-01-01T00:00:01Z',
              completed_at: null,
            },
          },
        ],
        total: 1,
        limit: 100,
        offset: 0,
      });
    if (url.endsWith('/sources/web'))
      return json({ ...source, source_type: 'webpage', processing_status: 'queued' }, 202);
    return json({});
  });
  renderRoute(<SourcesPage />, '/projects/project-1/sources');
  expect(await screen.findByText('indexing')).toBeInTheDocument();
  expect(screen.getByText('indexing · 65%')).toBeInTheDocument();
  expect(screen.getByText(/Recovered after restart 1 time/)).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'Webpage' }));
  await userEvent.type(screen.getByLabelText('HTTPS URL'), 'https://example.org/report');
  await userEvent.click(screen.getByRole('button', { name: 'Add webpage' }));
  await waitFor(() =>
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/sources/web'),
      expect.objectContaining({ method: 'POST' }),
    ),
  );
});

test('uploads a source file', async () => {
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    if (String(input).endsWith('/sources') && !init?.method)
      return json({ items: [], total: 0, limit: 100, offset: 0 });
    return json({ ...source, processing_status: 'uploaded' }, 202);
  });
  renderRoute(<SourcesPage />, '/projects/project-1/sources');
  await screen.findByText('No sources collected');
  await userEvent.click(screen.getByRole('button', { name: 'Upload' }));
  const file = new File(['synthetic'], 'evidence.txt', { type: 'text/plain' });
  await userEvent.upload(screen.getByLabelText('PDF, Markdown, or text file'), file);
  fireEvent.submit(screen.getByRole('button', { name: 'Upload and process' }).closest('form')!);
  await waitFor(() =>
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/sources/upload'),
      expect.objectContaining({ method: 'POST', body: expect.any(FormData) }),
    ),
  );
});

test('shows immutable source correction history and mapping confidence', async () => {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input);
    if (url.endsWith('/jobs')) {
      return json([
        {
          id: 'job-1',
          source_id: 'source-1',
          status: 'complete',
          stage: 'complete',
          progress: 1,
          attempt: 1,
          recovery_count: 1,
          error: null,
          created_at: '2032-01-01T00:00:00Z',
          started_at: '2032-01-01T00:00:01Z',
          completed_at: '2032-01-01T00:00:02Z',
        },
      ]);
    }
    if (url.endsWith('/content')) {
      return json({
        source_id: 'source-1',
        raw_text: 'Boardings were 8,240.',
        normalized_text: 'Boardings were 8,240.',
        corrected_text: 'Boardings were 8,241.',
        correction_note: 'Reviewed transcription.',
        correction_revision: 1,
        correction_history: [
          {
            id: 'revision-1',
            revision: 1,
            correction_note: 'Reviewed transcription.',
            previous_text_hash: 'a'.repeat(64),
            corrected_text_hash: 'b'.repeat(64),
            alignment_method: 'character-sequence-v1',
            alignment_confidence: 0.98,
            location_status: 'aligned',
            created_at: '2032-01-02T12:00:00Z',
          },
        ],
        page_count: null,
      });
    }
    return json(source);
  });
  renderRoute(<p>Fallback</p>, '/projects/project-1/sources/source-1', [
    {
      path: '/projects/:projectId/sources/:sourceId',
      element: <SourceDetailPage />,
    },
  ]);

  expect(await screen.findByText('Correction history')).toBeInTheDocument();
  expect(screen.getByText('Current text revision 1')).toBeInTheDocument();
  expect(screen.getByText('Revision 1')).toBeInTheDocument();
  expect(screen.getByText('Reviewed transcription.')).toBeInTheDocument();
  expect(screen.getByText(/98% · character-sequence-v1/)).toBeInTheDocument();
  expect(screen.getByText('aligned locations')).toBeInTheDocument();
  expect(screen.getByText('Processing trail')).toBeInTheDocument();
  expect(screen.getByText('Attempt 1')).toBeInTheDocument();
  expect(screen.getByText('Restart recoveries: 1')).toBeInTheDocument();
});
