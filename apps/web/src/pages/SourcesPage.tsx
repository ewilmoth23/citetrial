import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { FilePlus2, Globe2, NotebookPen, Upload } from 'lucide-react';
import { useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api } from '../api/client';
import {
  EmptyState,
  ErrorState,
  LoadingState,
  Modal,
  Notice,
  PageHeader,
  StatusBadge,
} from '../components/ui';

type AddMode = 'web' | 'file' | 'note' | null;

export function SourcesPage() {
  const { projectId = '' } = useParams();
  const client = useQueryClient();
  const [mode, setMode] = useState<AddMode>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const sources = useQuery({
    queryKey: ['sources', projectId],
    queryFn: () => api.listSources(projectId),
    refetchInterval: (query) =>
      query.state.data?.items.some(
        (source) => !['ready', 'ready_with_warnings', 'failed'].includes(source.processing_status),
      )
        ? 1500
        : false,
  });
  const addWeb = useMutation({
    mutationFn: (url: string) => api.addWebSource(projectId, url),
    onSuccess: () => done(),
  });
  const upload = useMutation({
    mutationFn: (file: File) => api.uploadSource(projectId, file),
    onSuccess: () => done(),
  });
  const addNote = useMutation({
    mutationFn: (body: { title: string; content: string }) => api.addNoteSource(projectId, body),
    onSuccess: () => done(),
  });
  const done = () => {
    setMode(null);
    void client.invalidateQueries({ queryKey: ['sources', projectId] });
    void client.invalidateQueries({ queryKey: ['project', projectId] });
  };
  const activeError = addWeb.error ?? upload.error ?? addNote.error;
  return (
    <div>
      <PageHeader
        eyebrow="Source library"
        title="Evidence enters here."
        description="CiteTrail preserves original identity, extraction method, location, and warnings through every downstream workflow."
        actions={
          <>
            <button className="button-secondary" onClick={() => setMode('web')}>
              <Globe2 className="h-4 w-4" />
              Webpage
            </button>
            <button className="button-secondary" onClick={() => setMode('file')}>
              <Upload className="h-4 w-4" />
              Upload
            </button>
            <button className="button-primary" onClick={() => setMode('note')}>
              <NotebookPen className="h-4 w-4" />
              Note source
            </button>
          </>
        }
      />
      <Notice>
        Imported source text is untrusted data. CiteTrail never executes webpage scripts, follows
        links, or bypasses access controls.
      </Notice>
      <div className="mt-5">
        {sources.isPending ? <LoadingState label="Loading source records…" /> : null}
        {sources.isError ? (
          <ErrorState error={sources.error} retry={() => void sources.refetch()} />
        ) : null}
      </div>
      {sources.data?.items.length === 0 ? (
        <div className="mt-5">
          <EmptyState
            title="No sources collected"
            description="Add an HTTPS webpage, upload a PDF/Markdown/text file, or write a note source. Processing and warnings appear here."
            action={
              <button className="button-primary" onClick={() => setMode('web')}>
                <FilePlus2 className="h-4 w-4" />
                Add the first source
              </button>
            }
          />
        </div>
      ) : null}
      {sources.data?.items.length ? (
        <div className="mt-5 overflow-hidden rounded-2xl border bg-white dark:bg-ink-900">
          <div className="hidden grid-cols-[minmax(0,2fr)_120px_160px_1fr] gap-4 border-b bg-paper-100 px-4 py-3 font-mono text-[10px] uppercase tracking-wide text-ink-500 md:grid">
            <span>Source</span>
            <span>Type</span>
            <span>State</span>
            <span>Context</span>
          </div>
          {sources.data.items.map((source) => (
            <Link
              key={source.id}
              to={source.id}
              className="grid gap-3 border-b p-4 last:border-b-0 hover:bg-paper-50 dark:hover:bg-ink-700 md:grid-cols-[minmax(0,2fr)_120px_160px_1fr] md:items-center"
            >
              <div className="min-w-0">
                <p className="truncate font-semibold">{source.title || source.original_name}</p>
                <p className="truncate text-xs text-ink-500">
                  {source.author || 'Author unknown'}
                  {source.publisher ? ` · ${source.publisher}` : ''}
                </p>
              </div>
              <p className="font-mono text-xs uppercase text-ink-500">{source.source_type}</p>
              <div>
                <StatusBadge status={source.processing_status} />
                {source.processing_job &&
                ['queued', 'running'].includes(source.processing_job.status) ? (
                  <div className="mt-2">
                    <p className="font-mono text-[10px] uppercase text-ink-500">
                      {source.processing_job.stage.replaceAll('_', ' ')} ·{' '}
                      {Math.round(source.processing_job.progress * 100)}%
                    </p>
                    <progress
                      className="mt-1 h-1.5 w-full accent-trail-500"
                      value={source.processing_job.progress}
                      max={1}
                      aria-label={`Processing ${source.title || source.original_name}`}
                    />
                  </div>
                ) : null}
              </div>
              <div className="text-xs text-ink-500">
                {source.publication_date ?? 'Date unknown'}
                {source.processing_job?.recovery_count ? (
                  <p className="mt-1 text-blue-700">
                    Recovered after restart {source.processing_job.recovery_count}{' '}
                    {source.processing_job.recovery_count === 1 ? 'time' : 'times'}
                  </p>
                ) : null}
                {source.warnings.length ? (
                  <p className="mt-1 text-amber-700">
                    {source.warnings.length} extraction warning
                    {source.warnings.length === 1 ? '' : 's'}
                  </p>
                ) : null}
                {source.duplicate_warnings.length ? (
                  <p className="mt-1 text-amber-700">Possible duplicate</p>
                ) : null}
              </div>
            </Link>
          ))}
        </div>
      ) : null}
      {mode ? (
        <Modal
          title={
            mode === 'web'
              ? 'Add a webpage'
              : mode === 'file'
                ? 'Upload a source'
                : 'Create a note source'
          }
          onClose={() => setMode(null)}
        >
          {mode === 'web' ? (
            <form
              className="space-y-4"
              onSubmit={(event) => {
                event.preventDefault();
                const data = new FormData(event.currentTarget);
                addWeb.mutate(String(data.get('url')));
              }}
            >
              <div>
                <label className="label" htmlFor="source-url">
                  HTTPS URL
                </label>
                <input
                  id="source-url"
                  name="url"
                  className="field"
                  type="url"
                  required
                  placeholder="https://example.org/report"
                />
                <p className="mt-2 text-xs leading-5 text-ink-500">
                  Local, private, link-local, metadata, and unsafe redirect targets are rejected.
                </p>
              </div>
              {activeError ? <ErrorState error={activeError} /> : null}
              <button className="button-primary" disabled={addWeb.isPending}>
                {addWeb.isPending ? 'Validating…' : 'Add webpage'}
              </button>
            </form>
          ) : null}
          {mode === 'file' ? (
            <form
              className="space-y-4"
              onSubmit={(event) => {
                event.preventDefault();
                const file = fileRef.current?.files?.[0];
                if (file) upload.mutate(file);
              }}
            >
              <div>
                <label className="label" htmlFor="source-file">
                  PDF, Markdown, or text file
                </label>
                <input
                  ref={fileRef}
                  id="source-file"
                  className="field file:mr-3 file:rounded-md file:border-0 file:bg-paper-100 file:px-3 file:py-1.5 file:text-sm"
                  type="file"
                  required
                  accept=".pdf,.md,.markdown,.txt,application/pdf,text/markdown,text/plain"
                />
                <p className="mt-2 text-xs text-ink-500">
                  Files are stored under collision-safe internal names outside the source tree.
                </p>
              </div>
              {activeError ? <ErrorState error={activeError} /> : null}
              <button className="button-primary" disabled={upload.isPending}>
                {upload.isPending ? 'Uploading…' : 'Upload and process'}
              </button>
            </form>
          ) : null}
          {mode === 'note' ? (
            <form
              className="space-y-4"
              onSubmit={(event) => {
                event.preventDefault();
                const data = new FormData(event.currentTarget);
                addNote.mutate({
                  title: String(data.get('title')),
                  content: String(data.get('content')),
                });
              }}
            >
              <div>
                <label className="label" htmlFor="note-title">
                  Title
                </label>
                <input id="note-title" name="title" className="field" required />
              </div>
              <div>
                <label className="label" htmlFor="note-content">
                  Note text
                </label>
                <textarea id="note-content" name="content" className="field min-h-48" required />
              </div>
              <Notice kind="warning">
                A note source is user-authored and is not presented as an external publication.
              </Notice>
              {activeError ? <ErrorState error={activeError} /> : null}
              <button className="button-primary" disabled={addNote.isPending}>
                Save note source
              </button>
            </form>
          ) : null}
        </Modal>
      ) : null}
    </div>
  );
}
