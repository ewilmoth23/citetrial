import { useMutation, useQuery } from '@tanstack/react-query';
import { Filter, Search as SearchIcon } from 'lucide-react';
import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api } from '../api/client';
import { EmptyState, ErrorState, Notice, PageHeader } from '../components/ui';
import type { SearchResult } from '../types/api';

function locationLabel(result: SearchResult) {
  if (result.location.page_number) return `Page ${result.location.page_number}`;
  if (result.location.heading_path) return result.location.heading_path;
  if (result.location.line_start)
    return `Lines ${result.location.line_start}–${result.location.line_end}`;
  return 'Source location preserved';
}

function resultTarget(projectId: string, result: SearchResult) {
  return `/projects/${projectId}/sources/${result.source_id}${result.location.page_number ? `?page=${result.location.page_number}` : ''}`;
}

export function SearchPage() {
  const { projectId = '' } = useParams();
  const [selected, setSelected] = useState<string[]>([]);
  const [searched, setSearched] = useState(false);
  const sources = useQuery({
    queryKey: ['sources', projectId],
    queryFn: () => api.listSources(projectId),
  });
  const search = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.search(projectId, body),
    onSettled: () => setSearched(true),
  });
  return (
    <div>
      <PageHeader
        eyebrow="Hybrid retrieval"
        title="Search the stored record."
        description="Lexical and local semantic retrieval are always project-scoped. Select individual sources to narrow the evidence boundary."
      />
      <form
        className="panel"
        onSubmit={(event) => {
          event.preventDefault();
          const data = new FormData(event.currentTarget);
          search.mutate({
            query: data.get('query'),
            mode: data.get('mode'),
            phrase: data.get('phrase') === 'on',
            source_ids: selected,
            limit: 15,
          });
        }}
      >
        <div className="flex flex-col gap-3 md:flex-row">
          <div className="relative flex-1">
            <SearchIcon className="absolute left-3 top-3.5 h-4 w-4 text-ink-500" />
            <input
              name="query"
              className="field pl-10"
              placeholder="Search for a claim, phrase, date, or organization…"
              required
            />
          </div>
          <select name="mode" className="field md:w-40" defaultValue="hybrid">
            <option value="hybrid">Hybrid</option>
            <option value="lexical">Full text</option>
            <option value="semantic">Semantic</option>
          </select>
          <button className="button-primary" disabled={search.isPending}>
            {search.isPending ? 'Searching…' : 'Search sources'}
          </button>
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <span className="inline-flex items-center gap-2 text-xs font-semibold">
            <Filter className="h-4 w-4" />
            Source boundary:
          </span>
          {sources.data?.items.map((source) => (
            <label
              key={source.id}
              className="inline-flex items-center gap-2 rounded-lg border px-2.5 py-1.5 text-xs"
            >
              <input
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
              {source.title || source.original_name}
            </label>
          ))}
          <label className="ml-auto inline-flex items-center gap-2 text-xs">
            <input type="checkbox" name="phrase" />
            Exact phrase
          </label>
        </div>
      </form>
      {selected.length ? (
        <div className="mt-4">
          <Notice>
            {selected.length} source{selected.length === 1 ? '' : 's'} selected. Results cannot
            cross this boundary.
          </Notice>
        </div>
      ) : null}
      {search.isError ? (
        <div className="mt-5">
          <ErrorState error={search.error} />
        </div>
      ) : null}
      {searched && search.data?.results.length === 0 ? (
        <div className="mt-5">
          <EmptyState
            title="No matching evidence"
            description="Try a broader term, switch retrieval mode, or clear the selected-source boundary."
          />
        </div>
      ) : null}
      {search.data?.results.length ? (
        <ol className="mt-5 space-y-4">
          {search.data.results.map((result, index) => (
            <li key={result.chunk_id} className="panel">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <p className="eyebrow">
                  Result {index + 1} · {result.method}
                </p>
                <span className="font-mono text-[10px] text-ink-500">
                  score {result.score.toFixed(4)}
                </span>
              </div>
              <blockquote className="mt-4 border-l-2 border-trail-500 pl-4 font-serif text-lg leading-8">
                {result.excerpt}
              </blockquote>
              <div className="mt-4 flex flex-wrap items-center gap-3 text-xs">
                <Link
                  className="font-semibold text-trail-700 hover:underline"
                  to={resultTarget(projectId, result)}
                >
                  {result.source_title}
                </Link>
                <span className="text-ink-500">{locationLabel(result)}</span>
                <span className="rounded bg-paper-100 px-2 py-1 font-mono uppercase text-ink-500 dark:bg-ink-700">
                  {result.source_type}
                </span>
              </div>
            </li>
          ))}
        </ol>
      ) : null}
    </div>
  );
}
