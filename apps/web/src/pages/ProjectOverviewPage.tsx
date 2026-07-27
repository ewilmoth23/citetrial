import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Archive, ArrowRight, Pencil, RotateCcw } from 'lucide-react';
import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { api } from '../api/client';
import { ErrorState, LoadingState, Metric, Modal, PageHeader, StatusBadge } from '../components/ui';

export function ProjectOverviewPage() {
  const { projectId = '' } = useParams();
  const navigate = useNavigate();
  const client = useQueryClient();
  const [editing, setEditing] = useState(false);
  const project = useQuery({
    queryKey: ['project', projectId],
    queryFn: () => api.getProject(projectId),
  });
  const history = useQuery({
    queryKey: ['history', projectId],
    queryFn: () => api.history(projectId),
  });
  const update = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.updateProject(projectId, body),
    onSuccess: () => {
      setEditing(false);
      void client.invalidateQueries({ queryKey: ['project', projectId] });
    },
  });
  const archive = useMutation({
    mutationFn: () => api.archiveProject(projectId),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['projects'] });
      navigate('/');
    },
  });
  const reopen = useMutation({
    mutationFn: () => api.reopenProject(projectId),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['project', projectId] });
      void client.invalidateQueries({ queryKey: ['projects'] });
    },
  });
  if (project.isPending) return <LoadingState />;
  if (project.isError)
    return <ErrorState error={project.error} retry={() => void project.refetch()} />;
  const value = project.data;
  return (
    <div>
      <PageHeader
        eyebrow="Project overview"
        title={value.title}
        description={value.primary_question}
        actions={
          <>
            <button className="button-secondary" onClick={() => setEditing(true)}>
              <Pencil className="h-4 w-4" />
              Edit
            </button>
            {value.status === 'archived' ? (
              <button className="button-secondary" onClick={() => reopen.mutate()}>
                <RotateCcw className="h-4 w-4" />
                Reopen
              </button>
            ) : (
              <button className="button-secondary" onClick={() => archive.mutate()}>
                <Archive className="h-4 w-4" />
                Archive
              </button>
            )}
          </>
        }
      />
      <div className="mb-6">
        <StatusBadge status={value.status} />
      </div>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Metric
          label="Sources ready"
          value={`${value.processed_source_count}/${value.source_count}`}
          note="Indexed with provenance"
        />
        <Metric
          label="Claims"
          value={value.claim_count}
          note={`${value.disputed_claim_count} disputed`}
        />
        <Metric
          label="Unresolved"
          value={value.unresolved_claim_count}
          note="Need more evidence or review"
        />
        <Metric
          label="Timeline events"
          value={value.timeline_event_count}
          note={value.brief_status ? `Brief ${value.brief_status}` : 'No brief yet'}
        />
      </div>
      <div className="mt-6 grid gap-6 xl:grid-cols-[1.4fr_1fr]">
        <section className="panel">
          <p className="eyebrow">Research frame</p>
          <h2 className="mt-3 font-serif text-2xl font-semibold">Question under investigation</h2>
          <blockquote className="mt-4 border-l-2 border-trail-500 pl-5 font-serif text-xl leading-8">
            {value.primary_question}
          </blockquote>
          {value.description ? (
            <p className="mt-5 text-sm leading-7 text-ink-500 dark:text-paper-200">
              {value.description}
            </p>
          ) : null}
          <div className="mt-6 flex flex-wrap gap-2">
            <Link className="button-primary" to="sources">
              Collect sources
              <ArrowRight className="h-4 w-4" />
            </Link>
            <Link className="button-secondary" to="claims">
              Review claims
            </Link>
          </div>
        </section>
        <section className="panel">
          <p className="eyebrow">Latest activity</p>
          <h2 className="mt-3 font-serif text-2xl font-semibold">Project trail</h2>
          <div className="mt-4 space-y-4">
            {history.data?.slice(0, 6).map((item) => (
              <div key={item.id} className="border-l pl-3">
                <p className="text-sm font-medium">{item.action.replaceAll('_', ' ')}</p>
                {item.detail ? (
                  <p className="truncate text-xs text-ink-500">{item.detail}</p>
                ) : null}
                <time className="font-mono text-[10px] text-ink-500">
                  {new Date(item.created_at).toLocaleString()}
                </time>
              </div>
            ))}
            {history.data?.length === 0 ? (
              <p className="text-sm text-ink-500">No activity yet.</p>
            ) : null}
          </div>
        </section>
      </div>
      {editing ? (
        <Modal title="Edit project" onClose={() => setEditing(false)}>
          <form
            className="space-y-4"
            onSubmit={(event) => {
              event.preventDefault();
              const data = new FormData(event.currentTarget);
              update.mutate({
                title: data.get('title'),
                primary_question: data.get('question'),
                description: data.get('description'),
              });
            }}
          >
            <div>
              <label className="label" htmlFor="edit-title">
                Title
              </label>
              <input
                id="edit-title"
                name="title"
                className="field"
                defaultValue={value.title}
                required
              />
            </div>
            <div>
              <label className="label" htmlFor="edit-question">
                Research question
              </label>
              <textarea
                id="edit-question"
                name="question"
                className="field min-h-28"
                defaultValue={value.primary_question}
                required
              />
            </div>
            <div>
              <label className="label" htmlFor="edit-description">
                Description
              </label>
              <textarea
                id="edit-description"
                name="description"
                className="field min-h-24"
                defaultValue={value.description ?? ''}
              />
            </div>
            {update.isError ? <ErrorState error={update.error} /> : null}
            <button className="button-primary" disabled={update.isPending}>
              Save changes
            </button>
          </form>
        </Modal>
      ) : null}
    </div>
  );
}
