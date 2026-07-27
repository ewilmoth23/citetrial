import type { ReactNode } from 'react';
import { AlertTriangle, CheckCircle2, LoaderCircle, SearchX } from 'lucide-react';
import { clsx } from 'clsx';

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <header className="mb-7 flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
      <div className="max-w-3xl">
        {eyebrow ? <p className="eyebrow mb-2">{eyebrow}</p> : null}
        <h1 className="font-serif text-3xl font-semibold leading-tight tracking-tight sm:text-4xl">
          {title}
        </h1>
        {description ? (
          <p className="mt-2 max-w-2xl text-sm leading-6 text-ink-500 dark:text-paper-200">
            {description}
          </p>
        ) : null}
      </div>
      {actions ? <div className="flex shrink-0 flex-wrap gap-2">{actions}</div> : null}
    </header>
  );
}

export function LoadingState({ label = 'Loading research workspace…' }: { label?: string }) {
  return (
    <div
      className="panel flex min-h-40 items-center justify-center gap-3 text-sm text-ink-500"
      role="status"
    >
      <LoaderCircle className="h-5 w-5 animate-spin" aria-hidden="true" />
      {label}
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="panel flex min-h-56 flex-col items-center justify-center px-6 text-center">
      <SearchX className="mb-4 h-8 w-8 text-ink-500" aria-hidden="true" />
      <h2 className="font-serif text-xl font-semibold">{title}</h2>
      <p className="mt-2 max-w-md text-sm leading-6 text-ink-500 dark:text-paper-200">
        {description}
      </p>
      {action ? <div className="mt-5">{action}</div> : null}
    </div>
  );
}

export function ErrorState({ error, retry }: { error: unknown; retry?: () => void }) {
  const message = error instanceof Error ? error.message : 'Something went wrong.';
  return (
    <div
      className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-900 dark:border-red-900 dark:bg-red-950/40 dark:text-red-100"
      role="alert"
    >
      <div className="flex gap-3">
        <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0" aria-hidden="true" />
        <div>
          <p className="font-semibold">Couldn’t complete that request</p>
          <p className="mt-1">{message}</p>
        </div>
      </div>
      {retry ? (
        <button className="button-secondary mt-3" onClick={retry}>
          Try again
        </button>
      ) : null}
    </div>
  );
}

export function StatusBadge({ status }: { status: string }) {
  const ready = status === 'ready';
  const warning =
    status.includes('warning') || ['disputed', 'contradicted', 'failed'].includes(status);
  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 font-mono text-[10px] font-medium uppercase tracking-wide',
        ready && 'bg-trail-100 text-trail-700 dark:bg-trail-700/30 dark:text-trail-100',
        warning && 'bg-amber-50 text-amber-700 dark:bg-amber-700/20 dark:text-amber-200',
        !ready && !warning && 'bg-paper-100 text-ink-700 dark:bg-ink-700 dark:text-paper-200',
      )}
    >
      <span className="status-dot" aria-hidden="true" /> {status.replaceAll('_', ' ')}
    </span>
  );
}

export function Notice({
  kind = 'info',
  children,
}: {
  kind?: 'info' | 'warning' | 'success';
  children: ReactNode;
}) {
  return (
    <div
      className={clsx(
        'rounded-xl border p-3 text-sm leading-6',
        kind === 'info' &&
          'border-blue-200 bg-blue-50 text-blue-900 dark:border-blue-900 dark:bg-blue-950/40 dark:text-blue-100',
        kind === 'warning' &&
          'border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-100',
        kind === 'success' &&
          'border-trail-100 bg-trail-50 text-trail-700 dark:bg-trail-700/20 dark:text-trail-100',
      )}
    >
      {kind === 'success' ? (
        <CheckCircle2 className="mr-2 inline h-4 w-4" aria-hidden="true" />
      ) : null}
      {children}
    </div>
  );
}

export function Metric({
  label,
  value,
  note,
}: {
  label: string;
  value: number | string;
  note?: string;
}) {
  return (
    <div className="panel min-h-32">
      <p className="eyebrow">{label}</p>
      <p className="mt-3 font-serif text-4xl font-semibold">{value}</p>
      {note ? <p className="mt-2 text-xs text-ink-500">{note}</p> : null}
    </div>
  );
}

export function Modal({
  title,
  children,
  onClose,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink-950/55 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="modal-title"
    >
      <div className="max-h-[90vh] w-full max-w-xl overflow-auto rounded-2xl bg-paper-50 p-5 shadow-2xl dark:bg-ink-900">
        <div className="mb-5 flex items-center justify-between gap-4">
          <h2 id="modal-title" className="font-serif text-2xl font-semibold">
            {title}
          </h2>
          <button className="button-secondary" onClick={onClose} aria-label="Close dialog">
            Close
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
