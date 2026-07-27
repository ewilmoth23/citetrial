import {
  BookOpenText,
  Boxes,
  Clock3,
  Download,
  FileSearch,
  Files,
  History,
  LayoutDashboard,
  MessageSquareText,
  NotebookPen,
  Search,
  Settings,
} from 'lucide-react';
import { NavLink, Outlet, useParams } from 'react-router-dom';
import { clsx } from 'clsx';

const links = [
  ['Overview', '', LayoutDashboard],
  ['Sources', 'sources', Files],
  ['Search', 'search', Search],
  ['Research chat', 'chat', MessageSquareText],
  ['Claims', 'claims', FileSearch],
  ['Evidence matrix', 'evidence', Boxes],
  ['Timeline', 'timeline', Clock3],
  ['Notes', 'notes', NotebookPen],
  ['Brief builder', 'brief', BookOpenText],
  ['Exports', 'exports', Download],
  ['History', 'history', History],
  ['Settings', 'settings', Settings],
] as const;

export function ProjectLayout() {
  const { projectId = '' } = useParams();
  return (
    <div className="grid gap-8 lg:grid-cols-[210px_minmax(0,1fr)]">
      <aside aria-label="Project navigation" className="min-w-0">
        <nav className="flex gap-1 overflow-x-auto pb-2 lg:sticky lg:top-24 lg:flex-col lg:overflow-visible">
          {links.map(([label, path, Icon]) => (
            <NavLink
              key={label}
              end={!path}
              to={`/projects/${projectId}${path ? `/${path}` : ''}`}
              className={({ isActive }) =>
                clsx(
                  'flex shrink-0 items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                  isActive
                    ? 'bg-ink-950 text-paper-50 dark:bg-paper-100 dark:text-ink-950'
                    : 'text-ink-500 hover:bg-paper-100 hover:text-ink-950 dark:hover:bg-ink-900 dark:hover:text-paper-50',
                )
              }
            >
              <Icon className="h-4 w-4" aria-hidden="true" />
              {label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <section className="min-w-0">
        <Outlet />
      </section>
    </div>
  );
}
