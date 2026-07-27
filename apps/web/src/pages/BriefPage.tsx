import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { FilePenLine, RefreshCw, Save } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { api } from '../api/client';
import { EmptyState, ErrorState, Modal, Notice, PageHeader } from '../components/ui';
import type { BriefSection } from '../types/api';

function SectionEditor({
  section,
  onSave,
  onGenerate,
  busy,
}: {
  section: BriefSection;
  onSave: (content: string) => void;
  onGenerate: () => void;
  busy: boolean;
}) {
  const [content, setContent] = useState(section.content);
  useEffect(() => setContent(section.content), [section.content]);
  return (
    <section className="panel">
      <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
        <div>
          <p className="eyebrow">
            {section.origin} {section.user_edited ? '· preserved user edit' : ''}
          </p>
          <h2 className="mt-2 font-serif text-2xl font-semibold">{section.title}</h2>
        </div>
        <div className="flex gap-2">
          <button className="button-secondary" onClick={onGenerate} disabled={busy}>
            <RefreshCw className="h-4 w-4" />
            Generate section
          </button>
          <button
            className="button-primary"
            onClick={() => onSave(content)}
            disabled={busy || content === section.content}
          >
            <Save className="h-4 w-4" />
            Save
          </button>
        </div>
      </div>
      {section.generation_warning ? (
        <div className="mt-4">
          <Notice kind="warning">{section.generation_warning}</Notice>
        </div>
      ) : null}
      <textarea
        className="field mt-4 min-h-52 font-serif text-base leading-7"
        value={content}
        onChange={(event) => setContent(event.target.value)}
        aria-label={`${section.title} content`}
      />
    </section>
  );
}

export function BriefPage() {
  const { projectId = '' } = useParams();
  const [pendingReplacement, setPendingReplacement] = useState<BriefSection | null>(null);
  const client = useQueryClient();
  const briefs = useQuery({
    queryKey: ['briefs', projectId],
    queryFn: () => api.listBriefs(projectId),
  });
  const brief = briefs.data?.[0];
  const refresh = () => void client.invalidateQueries({ queryKey: ['briefs', projectId] });
  const create = useMutation({ mutationFn: () => api.createBrief(projectId), onSuccess: refresh });
  const save = useMutation({
    mutationFn: ({ sectionId, content }: { sectionId: string; content: string }) =>
      api.updateBriefSection(projectId, brief!.id, sectionId, { content }),
    onSuccess: refresh,
  });
  const generate = useMutation({
    mutationFn: ({ sectionId, force }: { sectionId: string; force: boolean }) =>
      api.generateBriefSection(projectId, brief!.id, sectionId, force),
    onSuccess: refresh,
  });
  const handleGenerate = (section: BriefSection) => {
    if (section.user_edited) {
      setPendingReplacement(section);
      return;
    }
    generate.mutate({ sectionId: section.id, force: false });
  };
  return (
    <div>
      <PageHeader
        eyebrow="Structured research brief"
        title="Compose without losing the trail."
        description="Generate one section at a time, inspect warnings, and preserve user edits unless replacement is explicitly confirmed."
        actions={
          !brief ? (
            <button className="button-primary" onClick={() => create.mutate()}>
              <FilePenLine className="h-4 w-4" />
              Create brief
            </button>
          ) : undefined
        }
      />
      <Notice kind="warning">
        Citations prove where source text is stored—not that a statement is true. Conflicts,
        limitations, and unresolved questions belong in the final brief.
      </Notice>
      {briefs.isError || save.isError || generate.isError ? (
        <div className="mt-5">
          <ErrorState error={briefs.error ?? save.error ?? generate.error} />
        </div>
      ) : null}
      {!brief && briefs.data ? (
        <div className="mt-5">
          <EmptyState
            title="No research brief yet"
            description="Create the standard section structure, then generate deterministic evidence summaries or write each section yourself."
            action={
              <button className="button-primary" onClick={() => create.mutate()}>
                Create structured brief
              </button>
            }
          />
        </div>
      ) : null}
      {brief ? (
        <div className="mt-6 space-y-5">
          {brief.sections
            .sort((a, b) => a.ordinal - b.ordinal)
            .map((section) => (
              <SectionEditor
                key={section.id}
                section={section}
                busy={save.isPending || generate.isPending}
                onSave={(content) => save.mutate({ sectionId: section.id, content })}
                onGenerate={() => handleGenerate(section)}
              />
            ))}
        </div>
      ) : null}
      {pendingReplacement ? (
        <Modal title="Replace preserved user edit?" onClose={() => setPendingReplacement(null)}>
          <p className="text-sm leading-6 text-ink-500 dark:text-paper-200">
            Regenerating “{pendingReplacement.title}” will replace the text you wrote. This cannot
            be undone from the brief editor.
          </p>
          <div className="mt-6 flex flex-wrap justify-end gap-2">
            <button
              className="button-secondary"
              onClick={() => setPendingReplacement(null)}
              disabled={generate.isPending}
            >
              Keep my edit
            </button>
            <button
              className="button-danger"
              onClick={() => {
                generate.mutate({ sectionId: pendingReplacement.id, force: true });
                setPendingReplacement(null);
              }}
              disabled={generate.isPending}
            >
              Replace and regenerate
            </button>
          </div>
        </Modal>
      ) : null}
    </div>
  );
}
