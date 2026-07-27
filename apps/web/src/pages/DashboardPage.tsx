import { useQuery } from '@tanstack/react-query';
import { ArrowRight, Archive, FolderPlus } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useSearchParams } from 'react-router-dom';
import { api } from '../api/client';
import { EmptyState, ErrorState, LoadingState, PageHeader, StatusBadge } from '../components/ui';

export function DashboardPage() {
  const [searchParams] = useSearchParams();
  const includeArchived = searchParams.get('archived') === 'true';
  const projects = useQuery({
    queryKey: ['projects', includeArchived],
    queryFn: () => api.listProjects(includeArchived),
  });
  return (
    <div>
      <PageHeader
        eyebrow="Local research workspace"
        title="Follow every claim back to its source."
        description="Collect material, preserve provenance, test claims against evidence, and build briefs whose citations open into the exact stored text."
        actions={
          <Link className="button-primary" to="/projects/new">
            <FolderPlus className="h-4 w-4" />
            Start a project
          </Link>
        }
      />
      <div className="mb-7 grid gap-4 rounded-2xl border bg-ink-950 p-6 text-paper-50 sm:grid-cols-3 dark:bg-ink-900">
        <div>
          <p className="eyebrow !text-trail-100">01 · Collect</p>
          <p className="mt-2 font-serif text-xl">Sources remain primary.</p>
        </div>
        <div>
          <p className="eyebrow !text-trail-100">02 · Connect</p>
          <p className="mt-2 font-serif text-xl">Evidence supports or challenges claims.</p>
        </div>
        <div>
          <p className="eyebrow !text-trail-100">03 · Compose</p>
          <p className="mt-2 font-serif text-xl">Briefs preserve the trail.</p>
        </div>
      </div>
      {projects.isPending ? <LoadingState label="Loading projects…" /> : null}
      {projects.isError ? (
        <ErrorState error={projects.error} retry={() => void projects.refetch()} />
      ) : null}
      {projects.data?.items.length === 0 ? (
        <EmptyState
          title="No research projects yet"
          description="Start with one focused question. You can add webpages, PDFs, Markdown, text, and your own notes next."
          action={
            <Link className="button-primary" to="/projects/new">
              Create your first project
            </Link>
          }
        />
      ) : null}
      {projects.data?.items.length ? (
        <div className="grid gap-4 xl:grid-cols-2">
          {projects.data.items.map((project) => (
            <Link
              key={project.id}
              to={`/projects/${project.id}`}
              className="panel group block transition-transform hover:-translate-y-0.5"
            >
              <div className="flex items-start justify-between gap-4">
                <StatusBadge status={project.status} />
                <ArrowRight className="h-5 w-5 text-ink-500 transition-transform group-hover:translate-x-1" />
              </div>
              <h2 className="mt-5 font-serif text-2xl font-semibold">{project.title}</h2>
              <p className="mt-2 line-clamp-2 text-sm leading-6 text-ink-500 dark:text-paper-200">
                {project.primary_question}
              </p>
              <div className="mt-6 flex flex-wrap gap-x-5 gap-y-2 border-t pt-4 font-mono text-[11px] uppercase tracking-wide text-ink-500">
                <span>{project.source_count} sources</span>
                <span>{project.claim_count} claims</span>
                <span>{project.timeline_event_count} events</span>
              </div>
            </Link>
          ))}
        </div>
      ) : null}
      <Link
        to={includeArchived ? '/' : '/?archived=true'}
        className="mt-6 inline-flex items-center gap-2 text-sm text-ink-500 hover:text-ink-950"
      >
        <Archive className="h-4 w-4" />
        {includeArchived ? 'Hide archived projects' : 'Show archived projects'}
      </Link>
    </div>
  );
}
