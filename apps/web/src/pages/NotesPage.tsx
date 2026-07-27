import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Plus, Search, Trash2 } from 'lucide-react';
import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api } from '../api/client';
import { EmptyState, ErrorState, Modal, PageHeader } from '../components/ui';

export function NotesPage() {
  const { projectId = '' } = useParams();
  const client = useQueryClient();
  const [query, setQuery] = useState('');
  const [adding, setAdding] = useState(false);
  const notes = useQuery({
    queryKey: ['notes', projectId, query],
    queryFn: () => api.listNotes(projectId, query),
  });
  const sources = useQuery({
    queryKey: ['sources', projectId],
    queryFn: () => api.listSources(projectId),
  });
  const claims = useQuery({
    queryKey: ['claims', projectId],
    queryFn: () => api.listClaims(projectId),
  });
  const timeline = useQuery({
    queryKey: ['timeline', projectId],
    queryFn: () => api.listTimeline(projectId),
  });
  const refresh = () => {
    setAdding(false);
    void client.invalidateQueries({ queryKey: ['notes', projectId] });
  };
  const create = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.createNote(projectId, body),
    onSuccess: refresh,
  });
  const update = useMutation({
    mutationFn: ({ id, content }: { id: string; content: string }) =>
      api.updateNote(projectId, id, { content }),
    onSuccess: refresh,
  });
  const remove = useMutation({
    mutationFn: (id: string) => api.deleteNote(projectId, id),
    onSuccess: refresh,
  });
  return (
    <div>
      <PageHeader
        eyebrow="Research notebook"
        title="Your notes stay visibly yours."
        description="Notes can link to sources, claims, or timeline events. They are never presented as external evidence unless you explicitly create a note source."
        actions={
          <button className="button-primary" onClick={() => setAdding(true)}>
            <Plus className="h-4 w-4" />
            New note
          </button>
        }
      />
      <label className="relative mb-5 block">
        <Search className="absolute left-3 top-3.5 h-4 w-4 text-ink-500" />
        <span className="sr-only">Search notes</span>
        <input
          className="field pl-10"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search user-authored notes…"
        />
      </label>
      {notes.isError ? <ErrorState error={notes.error} /> : null}
      {notes.data?.length === 0 ? (
        <EmptyState
          title="No notes found"
          description={
            query
              ? 'No user notes match this search.'
              : 'Capture an observation, question, or interpretation without turning it into a source claim.'
          }
        />
      ) : null}
      <div className="grid gap-4 xl:grid-cols-2">
        {notes.data?.map((note) => (
          <article key={note.id} className="panel">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="eyebrow">User-authored note</p>
                <h2 className="mt-2 font-serif text-2xl font-semibold">{note.title}</h2>
              </div>
              <button
                className="button-danger !px-3"
                aria-label={`Delete ${note.title}`}
                onClick={() => window.confirm('Delete this note?') && remove.mutate(note.id)}
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
            <div className="mt-3 flex flex-wrap gap-2 text-xs">
              {note.source_id ? (
                <Link
                  className="rounded bg-paper-100 px-2 py-1 dark:bg-ink-700"
                  to={`/projects/${projectId}/sources/${note.source_id}`}
                >
                  Linked source
                </Link>
              ) : null}
              {note.claim_id ? (
                <Link
                  className="rounded bg-paper-100 px-2 py-1 dark:bg-ink-700"
                  to={`/projects/${projectId}/claims`}
                >
                  Linked claim
                </Link>
              ) : null}
              {note.timeline_event_id ? (
                <Link
                  className="rounded bg-paper-100 px-2 py-1 dark:bg-ink-700"
                  to={`/projects/${projectId}/timeline`}
                >
                  Linked timeline event
                </Link>
              ) : null}
            </div>
            <textarea
              className="field mt-4 min-h-36 font-serif text-base leading-7"
              defaultValue={note.content}
              onBlur={(event) => {
                if (event.target.value !== note.content)
                  update.mutate({ id: note.id, content: event.target.value });
              }}
            />
            <p className="mt-2 font-mono text-[10px] text-ink-500">
              Autosaves on leaving the field · updated {new Date(note.updated_at).toLocaleString()}
            </p>
          </article>
        ))}
      </div>
      {adding ? (
        <Modal title="Create research note" onClose={() => setAdding(false)}>
          <form
            className="space-y-4"
            onSubmit={(event) => {
              event.preventDefault();
              const data = new FormData(event.currentTarget);
              create.mutate({
                title: data.get('title'),
                content: data.get('content'),
                source_id: data.get('source') || null,
                claim_id: data.get('claim') || null,
                timeline_event_id: data.get('timeline') || null,
              });
            }}
          >
            <div>
              <label className="label" htmlFor="new-note-title">
                Title
              </label>
              <input id="new-note-title" name="title" className="field" required />
            </div>
            <div>
              <label className="label" htmlFor="new-note-content">
                Note
              </label>
              <textarea id="new-note-content" name="content" className="field min-h-52" required />
            </div>
            <div className="grid gap-3 sm:grid-cols-3">
              <div>
                <label className="label" htmlFor="note-source-link">
                  Link source
                </label>
                <select id="note-source-link" name="source" className="field">
                  <option value="">None</option>
                  {sources.data?.items.map((source) => (
                    <option key={source.id} value={source.id}>
                      {source.title || source.original_name}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="label" htmlFor="note-claim-link">
                  Link claim
                </label>
                <select id="note-claim-link" name="claim" className="field">
                  <option value="">None</option>
                  {claims.data?.map((claim) => (
                    <option key={claim.id} value={claim.id}>
                      {claim.text}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="label" htmlFor="note-timeline-link">
                  Link event
                </label>
                <select id="note-timeline-link" name="timeline" className="field">
                  <option value="">None</option>
                  {timeline.data?.map((event) => (
                    <option key={event.id} value={event.id}>
                      {event.title}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            {create.isError ? <ErrorState error={create.error} /> : null}
            <button className="button-primary" disabled={create.isPending}>
              Save user note
            </button>
          </form>
        </Modal>
      ) : null}
    </div>
  );
}
