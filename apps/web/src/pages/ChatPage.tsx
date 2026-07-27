import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { BookMarked, MessageSquareText, Send } from 'lucide-react';
import { useMemo, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { Link, useParams } from 'react-router-dom';
import { api } from '../api/client';
import { EmptyState, ErrorState, Notice, PageHeader } from '../components/ui';

function citationTarget(projectId: string, sourceId: string, location: string | null) {
  const page = location?.match(/^page\s+(\d+)$/i)?.[1];
  return `/projects/${projectId}/sources/${sourceId}${page ? `?page=${page}` : ''}`;
}

export function ChatPage() {
  const { projectId = '' } = useParams();
  const client = useQueryClient();
  const [selected, setSelected] = useState<string[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const sources = useQuery({
    queryKey: ['sources', projectId],
    queryFn: () => api.listSources(projectId),
  });
  const conversations = useQuery({
    queryKey: ['conversations', projectId],
    queryFn: () => api.listConversations(projectId),
  });
  const current = useMemo(
    () => conversations.data?.find((item) => item.id === conversationId) ?? conversations.data?.[0],
    [conversations.data, conversationId],
  );
  const createConversation = useMutation({
    mutationFn: () => api.createConversation(projectId, selected),
    onSuccess: (value) => {
      setConversationId(value.id);
      void client.invalidateQueries({ queryKey: ['conversations', projectId] });
    },
  });
  const ask = useMutation({
    mutationFn: async (question: string) => {
      const conversation = current ?? (await api.createConversation(projectId, selected));
      setConversationId(conversation.id);
      return api.askQuestion(projectId, conversation.id, question, selected);
    },
    onSuccess: () => void client.invalidateQueries({ queryKey: ['conversations', projectId] }),
  });
  const readySources =
    sources.data?.items.filter((item) =>
      ['ready', 'ready_with_warnings'].includes(item.processing_status),
    ) ?? [];
  return (
    <div>
      <PageHeader
        eyebrow="Grounded question answering"
        title="Ask only what the sources can answer."
        description="Citation labels are constructed from stored records. The model cannot create authoritative titles, page numbers, or source locations."
        actions={
          current ? (
            <button className="button-secondary" onClick={() => createConversation.mutate()}>
              <MessageSquareText className="h-4 w-4" />
              New conversation
            </button>
          ) : undefined
        }
      />
      <Notice kind="warning">
        Imported text may contain prompt injection. CiteTrail treats it as untrusted evidence and
        gives the model no tool access. Generated synthesis still requires review.
      </Notice>
      <div className="mt-5 grid gap-6 xl:grid-cols-[260px_minmax(0,1fr)]">
        <aside className="panel h-fit">
          <p className="eyebrow">Evidence boundary</p>
          <h2 className="mt-2 font-serif text-xl font-semibold">Selected sources</h2>
          <p className="mt-2 text-xs leading-5 text-ink-500">
            Select none to search every ready source in this project.
          </p>
          <div className="mt-4 space-y-2">
            {readySources.map((source) => (
              <label
                key={source.id}
                className="flex items-start gap-2 rounded-lg border p-2 text-xs"
              >
                <input
                  className="mt-0.5"
                  type="checkbox"
                  checked={selected.includes(source.id)}
                  onChange={(event) =>
                    setSelected((items) =>
                      event.target.checked
                        ? [...items, source.id]
                        : items.filter((id) => id !== source.id),
                    )
                  }
                />
                <span className="line-clamp-2">{source.title || source.original_name}</span>
              </label>
            ))}
          </div>
        </aside>
        <section className="min-w-0">
          <div className="panel min-h-[480px]">
            <div className="space-y-5" aria-live="polite">
              {!current?.messages.length && !ask.data ? (
                <EmptyState
                  title="No question asked yet"
                  description="Ask a focused question. If evidence is insufficient, CiteTrail says so rather than filling the gap with outside knowledge."
                />
              ) : null}
              {current?.messages.map((message) => (
                <article
                  key={message.id}
                  className={
                    message.role === 'user'
                      ? 'ml-auto max-w-[85%] rounded-2xl bg-ink-950 p-4 text-paper-50 dark:bg-ink-700'
                      : 'max-w-[92%]'
                  }
                >
                  {message.role === 'assistant' ? (
                    <p className="eyebrow mb-2">Generated synthesis · review required</p>
                  ) : null}
                  <div className="text-sm leading-7">
                    <ReactMarkdown skipHtml>{message.content}</ReactMarkdown>
                  </div>
                  {message.warning ? (
                    <div className="mt-3">
                      <Notice kind="warning">{message.warning}</Notice>
                    </div>
                  ) : null}
                  {message.citations.length ? (
                    <div className="mt-4 space-y-2">
                      {message.citations.map((citation) => (
                        <Link
                          key={citation.id}
                          to={citationTarget(projectId, citation.source_id, citation.location)}
                          className="block rounded-xl border bg-paper-50 p-3 text-ink-950 hover:border-trail-500 dark:bg-ink-950 dark:text-paper-50"
                        >
                          <span className="font-mono text-[10px] font-semibold text-trail-700 dark:text-trail-100">
                            {citation.marker} · {citation.source_title}
                          </span>
                          <p className="mt-1 line-clamp-2 font-serif text-sm">{citation.excerpt}</p>
                          <span className="mt-1 block text-[10px] text-ink-500">
                            {citation.location || 'Stored source location'} · text revision{' '}
                            {citation.source_revision ?? 0}
                          </span>
                        </Link>
                      ))}
                    </div>
                  ) : null}
                </article>
              ))}
            </div>
            <form
              className="mt-6 border-t pt-4"
              onSubmit={(event) => {
                event.preventDefault();
                const form = event.currentTarget;
                const data = new FormData(form);
                ask.mutate(String(data.get('question')), { onSuccess: () => form.reset() });
              }}
            >
              <label className="label" htmlFor="research-question">
                Question
              </label>
              <div className="flex gap-2">
                <textarea
                  id="research-question"
                  name="question"
                  className="field min-h-16 resize-y"
                  placeholder="What evidence describes the program's effect on weekday ridership?"
                  required
                />
                <button
                  className="button-primary self-end"
                  disabled={ask.isPending || readySources.length === 0}
                >
                  <Send className="h-4 w-4" />
                  {ask.isPending ? 'Grounding…' : 'Ask'}
                </button>
              </div>
              {readySources.length === 0 ? (
                <p className="mt-2 text-xs text-amber-700">
                  Add and process at least one source before asking a question.
                </p>
              ) : null}
            </form>
            {ask.isError ? (
              <div className="mt-4">
                <ErrorState error={ask.error} />
              </div>
            ) : null}
          </div>
          {ask.data && !ask.data.provider_available ? (
            <div className="mt-4">
              <Notice>
                <BookMarked className="mr-2 inline h-4 w-4" />
                The model provider is unavailable. The answer shows deterministic retrieved
                evidence, and all manual research tools remain available.
              </Notice>
            </div>
          ) : null}
        </section>
      </div>
    </div>
  );
}
