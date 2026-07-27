import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link2, Plus, ShieldQuestion, Trash2 } from 'lucide-react';
import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { api } from '../api/client';
import { EmptyState, ErrorState, Modal, PageHeader, StatusBadge } from '../components/ui';
import type { Claim } from '../types/api';

export function ClaimsPage() {
  const { projectId = '' } = useParams();
  const client = useQueryClient();
  const [adding, setAdding] = useState(false);
  const [evidenceClaim, setEvidenceClaim] = useState<Claim | null>(null);
  const claims = useQuery({
    queryKey: ['claims', projectId],
    queryFn: () => api.listClaims(projectId),
  });
  const sources = useQuery({
    queryKey: ['sources', projectId],
    queryFn: () => api.listSources(projectId),
  });
  const refresh = () => {
    setAdding(false);
    setEvidenceClaim(null);
    void client.invalidateQueries({ queryKey: ['claims', projectId] });
    void client.invalidateQueries({ queryKey: ['project', projectId] });
  };
  const create = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.createClaim(projectId, body),
    onSuccess: refresh,
  });
  const connect = useMutation({
    mutationFn: ({ claimId, body }: { claimId: string; body: Record<string, unknown> }) =>
      api.connectEvidence(projectId, claimId, body),
    onSuccess: refresh,
  });
  const remove = useMutation({
    mutationFn: (claimId: string) => api.deleteClaim(projectId, claimId),
    onSuccess: refresh,
  });
  return (
    <div>
      <PageHeader
        eyebrow="Claim ledger"
        title="Claims are propositions, not verdicts."
        description="A claim stays proposed until you review its supporting, contradicting, contextual, and uncertain evidence."
        actions={
          <button className="button-primary" onClick={() => setAdding(true)}>
            <Plus className="h-4 w-4" />
            New claim
          </button>
        }
      />
      {claims.isError ? <ErrorState error={claims.error} /> : null}
      {claims.data?.length === 0 ? (
        <EmptyState
          title="No claims recorded"
          description="Turn a research finding into a proposition, then link exact evidence excerpts from stored sources."
          action={
            <button className="button-primary" onClick={() => setAdding(true)}>
              Create a claim
            </button>
          }
        />
      ) : null}
      <div className="space-y-4">
        {claims.data?.map((claim) => (
          <article key={claim.id} className="panel">
            <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <StatusBadge status={claim.status} />
                  <span className="rounded bg-paper-100 px-2 py-1 font-mono text-[10px] uppercase text-ink-500 dark:bg-ink-700">
                    {claim.claim_type}
                  </span>
                </div>
                <h2 className="mt-4 font-serif text-2xl font-semibold leading-8">{claim.text}</h2>
                {claim.user_notes ? (
                  <p className="mt-2 text-sm text-ink-500">{claim.user_notes}</p>
                ) : null}
              </div>
              <div className="flex shrink-0 gap-2">
                <button className="button-secondary" onClick={() => setEvidenceClaim(claim)}>
                  <Link2 className="h-4 w-4" />
                  Link evidence
                </button>
                <button
                  className="button-danger !px-3"
                  aria-label="Delete claim"
                  onClick={() =>
                    window.confirm('Delete this claim and its evidence links?') &&
                    remove.mutate(claim.id)
                  }
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            </div>
            <div className="mt-5 grid gap-3 border-t pt-4 sm:grid-cols-4">
              {(['supports', 'contradicts', 'contextualizes', 'uncertain'] as const).map(
                (relationship) => (
                  <div key={relationship}>
                    <p className="font-mono text-[10px] uppercase tracking-wide text-ink-500">
                      {relationship}
                    </p>
                    <p className="mt-1 font-serif text-xl">
                      {
                        claim.evidence.filter((item) => item.relationship_type === relationship)
                          .length
                      }
                    </p>
                  </div>
                ),
              )}
            </div>
          </article>
        ))}
      </div>
      {adding ? (
        <Modal title="Create research claim" onClose={() => setAdding(false)}>
          <form
            className="space-y-4"
            onSubmit={(event) => {
              event.preventDefault();
              const data = new FormData(event.currentTarget);
              create.mutate({
                text: data.get('text'),
                claim_type: data.get('type'),
                status: 'proposed',
                user_notes: data.get('notes') || null,
              });
            }}
          >
            <div>
              <label className="label" htmlFor="claim-text">
                Claim or unresolved question
              </label>
              <textarea id="claim-text" name="text" className="field min-h-28" required />
            </div>
            <div>
              <label className="label" htmlFor="claim-type">
                Claim type
              </label>
              <select id="claim-type" name="type" className="field">
                <option value="factual">Factual</option>
                <option value="causal">Causal</option>
                <option value="interpretive">Interpretive</option>
                <option value="comparative">Comparative</option>
                <option value="chronological">Chronological</option>
                <option value="unresolved_question">Unresolved question</option>
              </select>
            </div>
            <div>
              <label className="label" htmlFor="claim-notes">
                User notes
              </label>
              <textarea id="claim-notes" name="notes" className="field min-h-20" />
            </div>
            {create.isError ? <ErrorState error={create.error} /> : null}
            <button className="button-primary" disabled={create.isPending}>
              Create proposed claim
            </button>
          </form>
        </Modal>
      ) : null}
      {evidenceClaim ? (
        <Modal title="Link verified evidence" onClose={() => setEvidenceClaim(null)}>
          <form
            className="space-y-4"
            onSubmit={(event) => {
              event.preventDefault();
              const data = new FormData(event.currentTarget);
              connect.mutate({
                claimId: evidenceClaim.id,
                body: {
                  source_id: data.get('source'),
                  excerpt: data.get('excerpt'),
                  relationship_type: data.get('relationship'),
                  origin: 'user',
                  notes: data.get('notes') || null,
                },
              });
            }}
          >
            <p className="rounded-xl bg-paper-100 p-3 font-serif dark:bg-ink-950">
              {evidenceClaim.text}
            </p>
            <div>
              <label className="label" htmlFor="evidence-source">
                Stored source
              </label>
              <select id="evidence-source" name="source" className="field" required>
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
              <label className="label" htmlFor="relationship">
                Relationship
              </label>
              <select id="relationship" name="relationship" className="field">
                <option value="supports">Supports</option>
                <option value="contradicts">Contradicts</option>
                <option value="contextualizes">Contextualizes</option>
                <option value="uncertain">Uncertain</option>
              </select>
            </div>
            <div>
              <label className="label" htmlFor="evidence-excerpt">
                Exact excerpt
              </label>
              <textarea
                id="evidence-excerpt"
                name="excerpt"
                className="field min-h-28 font-serif"
                required
              />
              <p className="mt-2 text-xs text-ink-500">
                Copy the exact excerpt from the source detail or search result. The API rejects
                unmatched text.
              </p>
            </div>
            <div>
              <label className="label" htmlFor="evidence-notes">
                Review note
              </label>
              <textarea id="evidence-notes" name="notes" className="field min-h-20" />
            </div>
            {connect.isError ? <ErrorState error={connect.error} /> : null}
            <button className="button-primary" disabled={connect.isPending}>
              <ShieldQuestion className="h-4 w-4" />
              Verify and link
            </button>
          </form>
        </Modal>
      ) : null}
    </div>
  );
}
