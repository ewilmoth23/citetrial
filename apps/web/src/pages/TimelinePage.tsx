import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { CalendarPlus, Check, X } from 'lucide-react';
import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { api } from '../api/client';
import { EmptyState, ErrorState, Modal, Notice, PageHeader, StatusBadge } from '../components/ui';

export function TimelinePage() {
  const { projectId = '' } = useParams();
  const client = useQueryClient();
  const [adding, setAdding] = useState(false);
  const events = useQuery({
    queryKey: ['timeline', projectId],
    queryFn: () => api.listTimeline(projectId),
  });
  const sources = useQuery({
    queryKey: ['sources', projectId],
    queryFn: () => api.listSources(projectId),
  });
  const refresh = () => {
    setAdding(false);
    void client.invalidateQueries({ queryKey: ['timeline', projectId] });
    void client.invalidateQueries({ queryKey: ['project', projectId] });
  };
  const create = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.createTimelineEvent(projectId, body),
    onSuccess: refresh,
  });
  const review = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) =>
      api.updateTimelineEvent(projectId, id, { review_status: status }),
    onSuccess: refresh,
  });
  return (
    <div>
      <PageHeader
        eyebrow="Evidence-backed chronology"
        title="Keep date precision honest."
        description="Approximate dates remain approximate. Suggested events require source evidence and stay visibly pending until reviewed."
        actions={
          <button className="button-primary" onClick={() => setAdding(true)}>
            <CalendarPlus className="h-4 w-4" />
            Add event
          </button>
        }
      />
      <Notice>
        A timeline date is a research statement. Open its linked excerpt before relying on it in a
        brief.
      </Notice>
      {events.isError ? (
        <div className="mt-5">
          <ErrorState error={events.error} />
        </div>
      ) : null}
      {events.data?.length === 0 ? (
        <div className="mt-5">
          <EmptyState
            title="No timeline events"
            description="Create a manual event or review a model-suggested event after verifying its evidence and date precision."
          />
        </div>
      ) : null}
      <ol className="relative mt-6 space-y-0 border-l-2 border-paper-200 pl-7 dark:border-ink-700">
        {events.data?.map((event) => (
          <li key={event.id} className="relative pb-8">
            <span className="absolute -left-[35px] top-1 h-4 w-4 rounded-full border-4 border-paper-50 bg-trail-500 dark:border-ink-950" />
            <div className="panel">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="eyebrow">
                    {event.date_label || event.date_start || 'Date unknown'} ·{' '}
                    {event.date_precision.replaceAll('_', ' ')}
                  </p>
                  <h2 className="mt-2 font-serif text-2xl font-semibold">{event.title}</h2>
                </div>
                <StatusBadge status={event.review_status} />
              </div>
              <p className="mt-3 text-sm leading-7 text-ink-700 dark:text-paper-200">
                {event.description}
              </p>
              {event.evidence.length ? (
                <div className="mt-4 space-y-2">
                  {event.evidence.map((evidence) => (
                    <blockquote
                      key={evidence.id}
                      className="rounded-lg border bg-paper-50 p-3 font-serif text-sm dark:bg-ink-950"
                    >
                      {evidence.excerpt}
                      <footer className="mt-2 font-mono text-[10px] text-ink-500">
                        Source {evidence.source_id}{' '}
                        {evidence.location ? `· ${evidence.location}` : ''} · text revision{' '}
                        {evidence.source_revision ?? 0}
                      </footer>
                    </blockquote>
                  ))}
                </div>
              ) : (
                <p className="mt-4 text-xs text-ink-500">
                  User-created event without external evidence.
                </p>
              )}
              {event.review_status === 'suggested' ? (
                <div className="mt-4 flex gap-2">
                  <button
                    className="button-primary"
                    onClick={() => review.mutate({ id: event.id, status: 'accepted' })}
                  >
                    <Check className="h-4 w-4" />
                    Accept
                  </button>
                  <button
                    className="button-secondary"
                    onClick={() => review.mutate({ id: event.id, status: 'rejected' })}
                  >
                    <X className="h-4 w-4" />
                    Reject
                  </button>
                </div>
              ) : null}
            </div>
          </li>
        ))}
      </ol>
      {adding ? (
        <Modal title="Add timeline event" onClose={() => setAdding(false)}>
          <form
            className="space-y-4"
            onSubmit={(event) => {
              event.preventDefault();
              const data = new FormData(event.currentTarget);
              const precision = String(data.get('precision'));
              create.mutate({
                title: data.get('title'),
                date_start: data.get('date') || null,
                date_label: data.get('label') || null,
                date_precision: precision,
                description: data.get('description'),
                origin: 'user',
                review_status: 'accepted',
                evidence: [{ source_id: data.get('source'), excerpt: data.get('excerpt') }],
              });
            }}
          >
            <div>
              <label className="label" htmlFor="event-title">
                Event title
              </label>
              <input id="event-title" name="title" className="field" required />
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <label className="label" htmlFor="event-date">
                  Normalized date
                </label>
                <input id="event-date" name="date" className="field" type="date" />
              </div>
              <div>
                <label className="label" htmlFor="date-precision">
                  Precision
                </label>
                <select id="date-precision" name="precision" className="field">
                  <option value="exact_day">Exact day</option>
                  <option value="month">Month</option>
                  <option value="year">Year</option>
                  <option value="approximate">Approximate</option>
                  <option value="unknown">Unknown</option>
                </select>
              </div>
            </div>
            <div>
              <label className="label" htmlFor="date-label">
                Original date wording
              </label>
              <input
                id="date-label"
                name="label"
                className="field"
                placeholder="around late spring 2032"
              />
              <p className="mt-1 text-xs text-ink-500">
                Required for approximate dates. Use no exact date when precision is unknown.
              </p>
            </div>
            <div>
              <label className="label" htmlFor="event-description">
                Description
              </label>
              <textarea
                id="event-description"
                name="description"
                className="field min-h-28"
                required
              />
            </div>
            <div>
              <label className="label" htmlFor="timeline-source">
                Evidence source
              </label>
              <select id="timeline-source" name="source" className="field" required>
                <option value="">Choose a ready source</option>
                {sources.data?.items
                  .filter((item) =>
                    ['ready', 'ready_with_warnings'].includes(item.processing_status),
                  )
                  .map((source) => (
                    <option key={source.id} value={source.id}>
                      {source.title || source.original_name}
                    </option>
                  ))}
              </select>
            </div>
            <div>
              <label className="label" htmlFor="timeline-excerpt">
                Exact evidence excerpt
              </label>
              <textarea
                id="timeline-excerpt"
                name="excerpt"
                className="field min-h-24 font-serif"
                required
              />
              <p className="mt-1 text-xs text-ink-500">
                The API verifies this excerpt against the selected stored source.
              </p>
            </div>
            {create.isError ? <ErrorState error={create.error} /> : null}
            <button className="button-primary" disabled={create.isPending}>
              Add event
            </button>
          </form>
        </Modal>
      ) : null}
    </div>
  );
}
