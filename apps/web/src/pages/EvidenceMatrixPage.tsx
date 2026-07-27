import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AlertTriangle, CheckCircle2, CircleHelp, Compass } from 'lucide-react';
import { Link, useParams } from 'react-router-dom';
import { api } from '../api/client';
import { EmptyState, ErrorState, PageHeader, StatusBadge } from '../components/ui';
import type { Evidence } from '../types/api';

const groups = [
  ['supports', 'Supporting', CheckCircle2, 'text-evidence-support'],
  ['contradicts', 'Contradicting', AlertTriangle, 'text-evidence-contradict'],
  ['contextualizes', 'Context', Compass, 'text-evidence-context'],
  ['uncertain', 'Uncertain', CircleHelp, 'text-evidence-uncertain'],
] as const;

function EvidenceCard({ item, projectId }: { item: Evidence; projectId: string }) {
  const page = item.location?.match(/^page\s+(\d+)$/i)?.[1];
  return (
    <Link
      to={`/projects/${projectId}/sources/${item.source_id}${page ? `?page=${page}` : ''}`}
      className="block rounded-lg border bg-paper-50 p-3 text-xs hover:border-trail-500 dark:bg-ink-950"
    >
      <blockquote className="line-clamp-4 font-serif text-sm leading-6">{item.excerpt}</blockquote>
      <p className="mt-2 truncate font-semibold text-trail-700 dark:text-trail-100">
        {item.source_title || item.source_id}
      </p>
      <p className="text-ink-500">
        {item.location ? `${item.location} · ` : ''}text revision {item.source_revision ?? 0}
      </p>
    </Link>
  );
}

export function EvidenceMatrixPage() {
  const { projectId = '' } = useParams();
  const client = useQueryClient();
  const claims = useQuery({
    queryKey: ['claims', projectId],
    queryFn: () => api.listClaims(projectId),
  });
  const update = useMutation({
    mutationFn: ({
      claimId,
      evidenceId,
      relationship,
    }: {
      claimId: string;
      evidenceId: string;
      relationship: string;
    }) => api.updateEvidence(projectId, claimId, evidenceId, relationship),
    onSuccess: () => void client.invalidateQueries({ queryKey: ['claims', projectId] }),
  });
  return (
    <div>
      <PageHeader
        eyebrow="Evidence matrix"
        title="See agreement, conflict, and gaps together."
        description="The matrix provides context—it does not collapse source differences into a truth score or automatically choose a winner."
      />
      {claims.isError ? <ErrorState error={claims.error} /> : null}
      {claims.data?.length === 0 ? (
        <EmptyState
          title="The evidence matrix is empty"
          description="Create a claim and link verified excerpts to see supporting, contradicting, contextual, and uncertain evidence side by side."
        />
      ) : null}
      <div className="space-y-5">
        {claims.data?.map((claim) => (
          <section key={claim.id} className="panel">
            <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
              <h2 className="max-w-3xl font-serif text-xl font-semibold">{claim.text}</h2>
              <StatusBadge status={claim.status} />
            </div>
            <div className="grid gap-3 xl:grid-cols-4">
              {groups.map(([key, label, Icon, color]) => {
                const items = claim.evidence.filter(
                  (evidence) => evidence.relationship_type === key,
                );
                return (
                  <div key={key} className="rounded-xl border p-3">
                    <h3
                      className={`mb-3 flex items-center gap-2 font-mono text-[10px] font-semibold uppercase tracking-wide ${color}`}
                    >
                      <Icon className="h-4 w-4" />
                      {label} · {items.length}
                    </h3>
                    <div className="space-y-2">
                      {items.map((item) => (
                        <div key={item.id}>
                          <EvidenceCard item={item} projectId={projectId} />
                          <select
                            aria-label={`Change relationship for evidence from ${item.source_title}`}
                            className="field mt-1 !min-h-8 !py-1 text-xs"
                            value={item.relationship_type}
                            onChange={(event) =>
                              update.mutate({
                                claimId: claim.id,
                                evidenceId: item.id,
                                relationship: event.target.value,
                              })
                            }
                          >
                            {groups.map(([value, title]) => (
                              <option key={value} value={value}>
                                {title}
                              </option>
                            ))}
                          </select>
                        </div>
                      ))}
                      {!items.length ? (
                        <p className="rounded-lg border border-dashed p-3 text-xs leading-5 text-ink-500">
                          Unresolved gap—no {label.toLowerCase()} evidence linked.
                        </p>
                      ) : null}
                    </div>
                  </div>
                );
              })}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}
