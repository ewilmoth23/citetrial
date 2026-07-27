import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  ArrowLeft,
  ExternalLink,
  FileWarning,
  History,
  RotateCcw,
  Save,
  Trash2,
  Workflow,
} from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { Document, Page, pdfjs } from 'react-pdf';
import { api, sourceFileUrl } from '../api/client';
import { ErrorState, LoadingState, Modal, Notice, PageHeader, StatusBadge } from '../components/ui';

pdfjs.GlobalWorkerOptions.workerSrc = `${new URL(
  'pdfjs-dist/build/pdf.worker.min.mjs',
  import.meta.url,
).toString()}?module=1`;

export function SourceDetailPage() {
  const { projectId = '', sourceId = '' } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const client = useQueryClient();
  const [correcting, setCorrecting] = useState(false);
  const [pdfPages, setPdfPages] = useState(0);
  const [pdfError, setPdfError] = useState<string | null>(null);
  const targetPage = Number(searchParams.get('page'));
  useEffect(() => {
    if (pdfPages > 0 && Number.isInteger(targetPage) && targetPage >= 1 && targetPage <= pdfPages) {
      document.getElementById(`pdf-page-${targetPage}`)?.scrollIntoView({ block: 'start' });
    }
  }, [pdfPages, targetPage]);
  const source = useQuery({
    queryKey: ['source', projectId, sourceId],
    queryFn: () => api.getSource(projectId, sourceId),
    refetchInterval: (query) =>
      query.state.data &&
      !['ready', 'ready_with_warnings', 'failed'].includes(query.state.data.processing_status)
        ? 1500
        : false,
  });
  const content = useQuery({
    queryKey: ['source-content', projectId, sourceId],
    queryFn: () => api.getSourceContent(projectId, sourceId),
    enabled: Boolean(
      source.data && ['ready', 'ready_with_warnings'].includes(source.data.processing_status),
    ),
    retry: false,
  });
  const jobs = useQuery({
    queryKey: ['source-jobs', projectId, sourceId],
    queryFn: () => api.getSourceJobs(projectId, sourceId),
    enabled: Boolean(source.data),
    refetchInterval: (query) =>
      query.state.data?.some((job) => ['queued', 'running'].includes(job.status)) ? 1500 : false,
  });
  const retry = useMutation({
    mutationFn: () => api.retrySource(projectId, sourceId),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['source', projectId, sourceId] });
      void client.invalidateQueries({ queryKey: ['source-jobs', projectId, sourceId] });
    },
  });
  const remove = useMutation({
    mutationFn: () => api.deleteSource(projectId, sourceId),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['sources', projectId] });
      navigate(`/projects/${projectId}/sources`);
    },
  });
  const correct = useMutation({
    mutationFn: ({ text, note }: { text: string; note: string }) =>
      api.correctSource(projectId, sourceId, text, note),
    onSuccess: () => {
      setCorrecting(false);
      void client.invalidateQueries({ queryKey: ['source-content', projectId, sourceId] });
      void client.invalidateQueries({ queryKey: ['source', projectId, sourceId] });
    },
  });
  const updateMetadata = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.updateSource(projectId, sourceId, body),
    onSuccess: () => void client.invalidateQueries({ queryKey: ['source', projectId, sourceId] }),
  });
  if (source.isPending) return <LoadingState />;
  if (source.isError)
    return <ErrorState error={source.error} retry={() => void source.refetch()} />;
  const item = source.data;
  return (
    <div>
      <Link
        to={`/projects/${projectId}/sources`}
        className="mb-5 inline-flex items-center gap-2 text-sm text-ink-500"
      >
        <ArrowLeft className="h-4 w-4" />
        Source library
      </Link>
      <PageHeader
        eyebrow={`${item.source_type} source`}
        title={item.title || item.original_name}
        description={
          item.author
            ? `${item.author}${item.publisher ? ` · ${item.publisher}` : ''}`
            : 'No explicit author metadata was found.'
        }
        actions={
          <>
            <StatusBadge status={item.processing_status} />
            {item.processing_status === 'failed' ? (
              <button className="button-secondary" onClick={() => retry.mutate()}>
                <RotateCcw className="h-4 w-4" />
                Retry
              </button>
            ) : null}
            <button
              className="button-danger"
              onClick={() =>
                window.confirm('Delete this source and its indexed evidence?') && remove.mutate()
              }
            >
              <Trash2 className="h-4 w-4" />
              Delete
            </button>
          </>
        }
      />
      {item.error_message ? <ErrorState error={new Error(item.error_message)} /> : null}
      {item.processing_job && ['queued', 'running'].includes(item.processing_job.status) ? (
        <div className="panel mb-5">
          <div className="flex items-start gap-3">
            <Workflow className="mt-0.5 h-5 w-5 shrink-0 text-trail-700 dark:text-trail-100" />
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <p className="eyebrow">Durable ingestion attempt {item.processing_job.attempt}</p>
                  <h2 className="mt-1 font-serif text-xl font-semibold">
                    {item.processing_job.stage.replaceAll('_', ' ')}
                  </h2>
                </div>
                <span className="font-mono text-xs text-ink-500">
                  {Math.round(item.processing_job.progress * 100)}%
                </span>
              </div>
              <progress
                className="mt-3 h-2 w-full accent-trail-500"
                value={item.processing_job.progress}
                max={1}
                aria-label="Source processing progress"
              />
              <p className="mt-2 text-xs leading-5 text-ink-500">
                This work is persisted in SQLite and resumes automatically after an interrupted
                application restart.
                {item.processing_job.recovery_count
                  ? ` It has been recovered ${item.processing_job.recovery_count} ${
                      item.processing_job.recovery_count === 1 ? 'time' : 'times'
                    }.`
                  : ''}
              </p>
            </div>
          </div>
        </div>
      ) : null}
      {item.warnings.length ? (
        <div className="mb-5 space-y-2">
          {item.warnings.map((warning) => (
            <Notice key={warning} kind="warning">
              <FileWarning className="mr-2 inline h-4 w-4" />
              {warning}
            </Notice>
          ))}
        </div>
      ) : null}
      <div className="grid gap-6 xl:grid-cols-[280px_minmax(0,1fr)]">
        <aside className="panel h-fit">
          <p className="eyebrow">Provenance record</p>
          <dl className="mt-4 space-y-4 text-sm">
            {[
              ['Original', item.original_name],
              ['Author', item.author || 'Unknown'],
              ['Publisher', item.publisher || 'Unknown'],
              ['Published', item.publication_date || 'Unknown'],
              [
                'Retrieved',
                item.retrieved_at ? new Date(item.retrieved_at).toLocaleString() : 'Not remote',
              ],
              ['Method', item.extraction_method || 'Pending'],
              ['Chunks', String(item.chunk_count)],
              ['SHA-256', item.content_hash ? `${item.content_hash.slice(0, 16)}…` : 'Pending'],
            ].map(([term, value]) => (
              <div key={term}>
                <dt className="font-mono text-[10px] uppercase tracking-wide text-ink-500">
                  {term}
                </dt>
                <dd className="mt-1 break-words">{value}</dd>
              </div>
            ))}
          </dl>
          {item.final_url ? (
            <a
              href={item.final_url}
              target="_blank"
              rel="noreferrer noopener"
              className="button-secondary mt-5 w-full"
            >
              <ExternalLink className="h-4 w-4" />
              Open original URL
            </a>
          ) : null}
          {jobs.data?.length ? (
            <div className="mt-6 border-t pt-5">
              <p className="eyebrow">Processing trail</p>
              <ol className="mt-3 space-y-3">
                {jobs.data.map((job) => (
                  <li key={job.id} className="rounded-lg border p-3 text-xs">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-semibold">Attempt {job.attempt}</span>
                      <StatusBadge status={job.status} />
                    </div>
                    <p className="mt-2 text-ink-500">
                      {job.stage.replaceAll('_', ' ')} · {Math.round(job.progress * 100)}%
                    </p>
                    {job.recovery_count ? (
                      <p className="mt-1 text-blue-700">Restart recoveries: {job.recovery_count}</p>
                    ) : null}
                    {job.error ? <p className="mt-1 text-red-700">{job.error}</p> : null}
                    <time className="mt-2 block font-mono text-[10px] text-ink-500">
                      {new Date(job.created_at).toLocaleString()}
                    </time>
                  </li>
                ))}
              </ol>
            </div>
          ) : null}
          <form
            className="mt-6 space-y-3 border-t pt-5"
            onSubmit={(event) => {
              event.preventDefault();
              const data = new FormData(event.currentTarget);
              updateMetadata.mutate({
                category: data.get('category') || null,
                importance: data.get('importance') || null,
                source_label: data.get('source_label') || null,
                trust_note: data.get('trust_note') || null,
              });
            }}
          >
            <p className="eyebrow">User context</p>
            <div>
              <label className="label" htmlFor="source-category">
                Category
              </label>
              <input
                id="source-category"
                name="category"
                className="field"
                defaultValue={item.category ?? ''}
                placeholder="government report"
              />
            </div>
            <div>
              <label className="label" htmlFor="source-importance">
                Importance
              </label>
              <select
                id="source-importance"
                name="importance"
                className="field"
                defaultValue={item.importance ?? ''}
              >
                <option value="">Not set</option>
                <option value="low">Low</option>
                <option value="normal">Normal</option>
                <option value="high">High</option>
                <option value="critical">Critical</option>
              </select>
            </div>
            <div>
              <label className="label" htmlFor="source-label">
                Source label
              </label>
              <select
                id="source-label"
                name="source_label"
                className="field"
                defaultValue={item.source_label ?? ''}
              >
                <option value="">Unknown</option>
                <option value="primary">Primary</option>
                <option value="secondary">Secondary</option>
              </select>
            </div>
            <div>
              <label className="label" htmlFor="trust-note">
                Trust note
              </label>
              <textarea
                id="trust-note"
                name="trust_note"
                className="field min-h-20"
                defaultValue={item.trust_note ?? ''}
              />
            </div>
            <button className="button-secondary w-full" disabled={updateMetadata.isPending}>
              {updateMetadata.isPending ? 'Saving…' : 'Save source context'}
            </button>
            {updateMetadata.isError ? <ErrorState error={updateMetadata.error} /> : null}
          </form>
        </aside>
        <section className="min-w-0 space-y-6">
          {item.source_type === 'pdf' &&
          ['ready', 'ready_with_warnings'].includes(item.processing_status) ? (
            <div className="panel max-h-[80vh] overflow-auto">
              <div className="mb-4 flex items-center justify-between">
                <div>
                  <p className="eyebrow">Original document</p>
                  <h2 className="mt-1 font-serif text-xl font-semibold">PDF viewer</h2>
                </div>
                <span className="text-xs text-ink-500">
                  {pdfPages
                    ? `${pdfPages} pages${targetPage ? ` · cited page ${targetPage}` : ''}`
                    : 'Loading…'}
                </span>
              </div>
              <Document
                file={sourceFileUrl(projectId, sourceId)}
                onLoadSuccess={({ numPages }) => {
                  setPdfError(null);
                  setPdfPages(numPages);
                }}
                onLoadError={(error) => {
                  setPdfPages(0);
                  setPdfError(error.message);
                }}
                loading={<LoadingState label="Opening local PDF…" />}
                error={
                  <Notice kind="warning">
                    The PDF viewer could not open this file. Extracted text remains available below.
                    {pdfError ? (
                      <span className="mt-2 block font-mono text-xs">{pdfError}</span>
                    ) : null}
                  </Notice>
                }
              >
                {Array.from({ length: pdfPages }, (_, index) => (
                  <div
                    id={`pdf-page-${index + 1}`}
                    key={index}
                    className={
                      targetPage === index + 1 ? 'mb-4 rounded-lg ring-4 ring-trail-500' : 'mb-4'
                    }
                  >
                    <Page
                      pageNumber={index + 1}
                      width={Math.min(760, window.innerWidth - 80)}
                      renderAnnotationLayer={false}
                      renderTextLayer
                    />
                  </div>
                ))}
              </Document>
            </div>
          ) : null}
          <div className="panel">
            <div className="mb-5 flex items-center justify-between gap-4">
              <div>
                <p className="eyebrow">Stored extraction</p>
                <h2 className="mt-1 font-serif text-2xl font-semibold">Searchable source text</h2>
                {content.data ? (
                  <p className="mt-1 text-xs text-ink-500">
                    Current text revision {content.data.correction_revision}
                  </p>
                ) : null}
              </div>
              {content.data ? (
                <button className="button-secondary" onClick={() => setCorrecting(true)}>
                  <Save className="h-4 w-4" />
                  Correct extraction
                </button>
              ) : null}
            </div>
            {content.isPending &&
            ['ready', 'ready_with_warnings'].includes(item.processing_status) ? (
              <LoadingState label="Loading extracted text…" />
            ) : null}
            {content.data ? (
              <div className="prose-source max-h-[70vh] overflow-auto rounded-xl border bg-paper-50 p-5 dark:bg-ink-950">
                {content.data.corrected_text || content.data.normalized_text}
              </div>
            ) : null}
            {!['ready', 'ready_with_warnings', 'failed'].includes(item.processing_status) ? (
              <LoadingState label={`Source is ${item.processing_status.replaceAll('_', ' ')}…`} />
            ) : null}
          </div>
          {content.data?.correction_history.length ? (
            <div className="panel">
              <div className="flex items-start gap-3">
                <History className="mt-1 h-5 w-5 shrink-0 text-trail-700 dark:text-trail-100" />
                <div>
                  <p className="eyebrow">Immutable revision ledger</p>
                  <h2 className="mt-1 font-serif text-2xl font-semibold">Correction history</h2>
                  <p className="mt-2 text-sm leading-6 text-ink-500">
                    Every saved correction remains auditable. Evidence and citations keep the text
                    revision they were attached to.
                  </p>
                </div>
              </div>
              <ol className="mt-5 space-y-3">
                {[...content.data.correction_history].reverse().map((revision) => (
                  <li
                    key={revision.id}
                    className="rounded-xl border bg-paper-50 p-4 dark:bg-ink-950"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <h3 className="font-semibold">Revision {revision.revision}</h3>
                        <time className="mt-1 block font-mono text-[10px] text-ink-500">
                          {new Date(revision.created_at).toLocaleString()}
                        </time>
                      </div>
                      <span className="rounded bg-paper-100 px-2 py-1 font-mono text-[10px] uppercase tracking-wide text-ink-500 dark:bg-ink-700">
                        {revision.location_status.replaceAll('_', ' ')} locations
                      </span>
                    </div>
                    <p className="mt-3 text-sm leading-6">{revision.correction_note}</p>
                    <dl className="mt-3 grid gap-2 border-t pt-3 text-xs sm:grid-cols-2">
                      <div>
                        <dt className="text-ink-500">Location mapping</dt>
                        <dd className="mt-1 font-mono">
                          {Math.round(revision.alignment_confidence * 100)}% ·{' '}
                          {revision.alignment_method}
                        </dd>
                      </div>
                      <div>
                        <dt className="text-ink-500">Text hash change</dt>
                        <dd className="mt-1 font-mono">
                          {revision.previous_text_hash.slice(0, 8)}… →{' '}
                          {revision.corrected_text_hash.slice(0, 8)}…
                        </dd>
                      </div>
                    </dl>
                  </li>
                ))}
              </ol>
            </div>
          ) : null}
        </section>
      </div>
      {correcting && content.data ? (
        <Modal title="Correct extracted text" onClose={() => setCorrecting(false)}>
          <form
            className="space-y-4"
            onSubmit={(event) => {
              event.preventDefault();
              const data = new FormData(event.currentTarget);
              correct.mutate({ text: String(data.get('text')), note: String(data.get('note')) });
            }}
          >
            <Notice kind="warning">
              The original extraction and every prior correction are preserved. Search moves to the
              new revision; existing evidence and citations retain their historical revision. PDF
              page locations are aligned when confidence is sufficient and otherwise left unmapped.
            </Notice>
            <div>
              <label className="label" htmlFor="corrected-text">
                Corrected text
              </label>
              <textarea
                id="corrected-text"
                name="text"
                className="field min-h-64 font-mono text-xs"
                defaultValue={content.data.corrected_text || content.data.normalized_text}
                required
              />
            </div>
            <div>
              <label className="label" htmlFor="correction-note">
                What changed?
              </label>
              <textarea
                id="correction-note"
                name="note"
                className="field min-h-20"
                defaultValue={content.data.correction_note ?? ''}
                required
              />
            </div>
            {correct.isError ? <ErrorState error={correct.error} /> : null}
            <button className="button-primary" disabled={correct.isPending}>
              Save corrected extraction
            </button>
          </form>
        </Modal>
      ) : null}
    </div>
  );
}
