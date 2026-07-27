import { BookOpenCheck, Moon, Plus, Sun } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link, Outlet } from 'react-router-dom';

export function AppLayout() {
  const [dark, setDark] = useState(() => localStorage.getItem('citetrail-theme') === 'dark');
  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark);
    localStorage.setItem('citetrail-theme', dark ? 'dark' : 'light');
  }, [dark]);
  return (
    <div className="min-h-screen">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-lg focus:bg-white focus:p-3"
      >
        Skip to content
      </a>
      <header className="sticky top-0 z-40 border-b bg-paper-50/95 backdrop-blur dark:bg-ink-950/95">
        <div className="mx-auto flex h-16 max-w-[1500px] items-center justify-between px-4 sm:px-6">
          <Link
            to="/"
            className="flex items-center gap-2 font-serif text-xl font-semibold tracking-tight"
          >
            <span className="grid h-9 w-9 place-items-center rounded-xl bg-ink-950 text-paper-50 dark:bg-trail-500 dark:text-ink-950">
              <BookOpenCheck className="h-5 w-5" />
            </span>
            CiteTrail
          </Link>
          <div className="flex items-center gap-2">
            <span className="hidden font-mono text-[10px] uppercase tracking-wider text-ink-500 sm:inline">
              Evidence before prose
            </span>
            <button
              className="button-secondary !px-3"
              onClick={() => setDark((value) => !value)}
              aria-label={`Use ${dark ? 'light' : 'dark'} theme`}
            >
              {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </button>
            <Link className="button-primary" to="/projects/new" aria-label="New project">
              <Plus className="h-4 w-4" aria-hidden="true" />{' '}
              <span className="hidden sm:inline">New project</span>
            </Link>
          </div>
        </div>
      </header>
      <main id="main-content" className="mx-auto max-w-[1500px] px-4 py-8 sm:px-6">
        <Outlet />
      </main>
    </div>
  );
}
