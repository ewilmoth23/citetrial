import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { api } from '../api/client';
import { EmptyState, ErrorState, LoadingState, PageHeader } from '../components/ui';

export function HistoryPage() {
  const { projectId = '' } = useParams();
  const history = useQuery({
    queryKey: ['history', projectId],
    queryFn: () => api.history(projectId),
  });
  return (
    <div>
      <PageHeader
        eyebrow="Project history"
        title="A readable trail of research actions."
        description="CiteTrail records high-level actions without logging private source bodies, notes, complete prompts, or secrets."
      />
      {history.isPending ? <LoadingState /> : null}
      {history.isError ? <ErrorState error={history.error} /> : null}
      {history.data?.length === 0 ? (
        <EmptyState
          title="No activity recorded"
          description="Project, source, claim, evidence, brief, export, and deletion actions appear here."
        />
      ) : null}
      <ol className="space-y-3">
        {history.data?.map((item) => (
          <li
            key={item.id}
            className="panel flex flex-col justify-between gap-2 sm:flex-row sm:items-center"
          >
            <div>
              <p className="font-semibold capitalize">{item.action.replaceAll('_', ' ')}</p>
              {item.detail ? (
                <p className="mt-1 break-all text-xs text-ink-500">{item.detail}</p>
              ) : null}
            </div>
            <time className="shrink-0 font-mono text-[10px] text-ink-500">
              {new Date(item.created_at).toLocaleString()}
            </time>
          </li>
        ))}
      </ol>
    </div>
  );
}
