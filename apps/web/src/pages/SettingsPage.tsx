import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Archive, Database, Download, HardDrive, Server, Trash2 } from 'lucide-react';
import { useNavigate, useParams } from 'react-router-dom';
import { api } from '../api/client';
import { ErrorState, LoadingState, Notice, PageHeader } from '../components/ui';

export function SettingsPage() {
  const { projectId = '' } = useParams();
  const navigate = useNavigate();
  const client = useQueryClient();
  const settings = useQuery({ queryKey: ['settings'], queryFn: api.getSettings });
  const health = useQuery({ queryKey: ['health'], queryFn: api.health, refetchInterval: 30000 });
  const backup = useMutation({
    mutationFn: api.createWorkspaceBackup,
    onSuccess: ({ blob, filename }) => {
      const objectUrl = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = objectUrl;
      link.download = filename;
      link.click();
      URL.revokeObjectURL(objectUrl);
    },
  });
  const remove = useMutation({
    mutationFn: () => api.deleteProject(projectId),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['projects'] });
      navigate('/');
    },
  });
  return (
    <div>
      <PageHeader
        eyebrow="Local application settings"
        title="Know where the research goes."
        description="Configuration is server-side. API keys are never returned to the browser, and remote providers receive only excerpts selected for a model task."
      />
      {settings.isPending ? <LoadingState /> : null}
      {settings.isError ? <ErrorState error={settings.error} /> : null}
      {settings.data ? (
        <div className="grid gap-5 lg:grid-cols-3">
          <section className="panel">
            <HardDrive className="h-6 w-6 text-trail-700" />
            <p className="eyebrow mt-4">Data storage</p>
            <p className="mt-2 break-all text-sm">{String(settings.data.data_dir)}</p>
            <p className="mt-2 text-xs text-ink-500">
              Uploads, SQLite metadata, and derived indexes stay outside the source tree by default.
            </p>
          </section>
          <section className="panel">
            <Server className="h-6 w-6 text-trail-700" />
            <p className="eyebrow mt-4">Model provider</p>
            <p className="mt-2 font-semibold">
              {String(settings.data.model_provider)} · {String(settings.data.model_name)}
            </p>
            <p className="mt-2 break-all text-xs text-ink-500">
              {String(settings.data.model_base_url)}
            </p>
            <p className="mt-2 text-xs text-ink-500">
              Requests leave device: {String(settings.data.provider_requests_leave_device)} · API
              key configured: {String(settings.data.model_api_key_configured)}
            </p>
          </section>
          <section className="panel">
            <Database className="h-6 w-6 text-trail-700" />
            <p className="eyebrow mt-4">Retrieval</p>
            <p className="mt-2 font-semibold">
              Semantic search: {String(settings.data.semantic_search_enabled)}
            </p>
            <p className="mt-2 text-xs text-ink-500">
              Embedding runtime: {String(settings.data.embedding_model)}
            </p>
          </section>
          <section className="panel">
            <HardDrive className="h-6 w-6 text-trail-700" />
            <p className="eyebrow mt-4">Ingestion boundaries</p>
            <p className="mt-2 text-sm">
              Upload: {Number(settings.data.max_upload_bytes).toLocaleString()} bytes
            </p>
            <p className="mt-1 text-sm">
              Download: {Number(settings.data.max_download_bytes).toLocaleString()} bytes
            </p>
            <p className="mt-2 text-xs text-ink-500">
              Timeout: {String(settings.data.request_timeout_seconds)}s · PDF pages:{' '}
              {String(settings.data.max_pdf_pages)} · OCR: {String(settings.data.ocr_mode)}
            </p>
            <p className="mt-2 text-xs text-ink-500">
              Queue: {String(settings.data.ingestion_worker_mode)} · poll{' '}
              {String(settings.data.ingestion_poll_seconds)}s
            </p>
          </section>
          <section className="panel">
            <Database className="h-6 w-6 text-trail-700" />
            <p className="eyebrow mt-4">Deterministic tools</p>
            <p className="mt-2 font-semibold">Available without a model</p>
            <p className="mt-2 text-xs text-ink-500">
              Collection, extraction, search, claims, evidence, timelines, notes, briefs, and
              exports.
            </p>
          </section>
          <section className="panel">
            <Server className="h-6 w-6 text-trail-700" />
            <p className="eyebrow mt-4">Remote disclosure</p>
            <p className="mt-2 text-sm">{String(settings.data.remote_provider_warning)}</p>
            <p className="mt-2 text-xs text-ink-500">
              Credentials remain server-side; only a configured/not-configured flag is returned.
            </p>
          </section>
          <section className="panel lg:col-span-3">
            <Archive className="h-6 w-6 text-trail-700" />
            <p className="eyebrow mt-4">Workspace resilience</p>
            <h2 className="mt-2 font-serif text-2xl font-semibold">
              Back up the complete evidence workspace
            </h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-ink-500">
              This creates a verified SQLite snapshot with every referenced upload and local vector
              file. The archive contains private research content; keep it encrypted and do not
              share it as a normal project export.
            </p>
            <button
              className="button-primary mt-5"
              type="button"
              onClick={() => backup.mutate()}
              disabled={backup.isPending}
            >
              <Download className="h-4 w-4" />
              {backup.isPending ? 'Building verified backup…' : 'Download workspace backup'}
            </button>
            {backup.isSuccess ? (
              <p className="mt-3 text-sm text-emerald-700 dark:text-emerald-300">
                Backup created. Store the downloaded .ctbackup file somewhere protected.
              </p>
            ) : null}
            {backup.isError ? (
              <div className="mt-4">
                <ErrorState error={backup.error} />
              </div>
            ) : null}
          </section>
        </div>
      ) : null}
      <div className="mt-5">
        <Notice kind={health.data && health.data.status === 'healthy' ? 'success' : 'warning'}>
          Application health: {health.data ? String(health.data.status) : 'checking…'}
        </Notice>
      </div>
      <section className="mt-8 rounded-2xl border border-red-200 bg-red-50 p-5 dark:border-red-900 dark:bg-red-950/20">
        <p className="eyebrow !text-red-700 dark:!text-red-300">Danger zone</p>
        <h2 className="mt-2 font-serif text-2xl font-semibold">Delete this project completely</h2>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-red-900 dark:text-red-100">
          This removes stored files, extracted documents, chunks, citations, claims, evidence,
          timeline events, notes, briefs, model-run records, exports, and project history. It cannot
          be undone.
        </p>
        <button
          className="button-danger mt-5"
          onClick={() => {
            const confirmation = window.prompt('Type DELETE to permanently remove this project.');
            if (confirmation === 'DELETE') remove.mutate();
          }}
          disabled={remove.isPending}
        >
          <Trash2 className="h-4 w-4" />
          {remove.isPending ? 'Deleting…' : 'Delete project'}
        </button>
        {remove.isError ? (
          <div className="mt-4">
            <ErrorState error={remove.error} />
          </div>
        ) : null}
      </section>
    </div>
  );
}
