import { Download, FileJson2, FileText } from 'lucide-react';
import { useParams } from 'react-router-dom';
import { exportUrl } from '../api/client';
import { Notice, PageHeader } from '../components/ui';

export function ExportsPage() {
  const { projectId = '' } = useParams();
  return (
    <div>
      <PageHeader
        eyebrow="Portable research record"
        title="Export the evidence trail."
        description="Exports include structured project data and limitations. They never include provider keys, hidden prompts, logs, or local absolute paths."
      />
      <Notice>
        Complete source text is excluded from JSON by default. Imported material stays local and is
        not republished.
      </Notice>
      <div className="mt-6 grid gap-5 lg:grid-cols-2">
        <section className="panel">
          <FileText className="h-7 w-7 text-trail-700" />
          <h2 className="mt-4 font-serif text-2xl font-semibold">Markdown research export</h2>
          <p className="mt-2 text-sm leading-6 text-ink-500">
            Project question, claims, evidence relationships, contradictions, timeline, notes, brief
            sections, source list, and limitations.
          </p>
          <a className="button-primary mt-5" href={exportUrl(projectId, 'markdown')} download>
            <Download className="h-4 w-4" />
            Download Markdown
          </a>
        </section>
        <section className="panel">
          <FileJson2 className="h-7 w-7 text-trail-700" />
          <h2 className="mt-4 font-serif text-2xl font-semibold">Structured JSON export</h2>
          <p className="mt-2 text-sm leading-6 text-ink-500">
            Machine-readable provenance and research records. Full source bodies remain excluded
            unless you choose the explicit option below.
          </p>
          <div className="mt-5 flex flex-wrap gap-2">
            <a className="button-primary" href={exportUrl(projectId, 'json')} download>
              <Download className="h-4 w-4" />
              Download JSON
            </a>
            <a
              className="button-secondary"
              href={exportUrl(projectId, 'json', '?include_full_text=true')}
              download
            >
              Include full source text
            </a>
          </div>
        </section>
      </div>
    </div>
  );
}
