import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, ArrowRight } from 'lucide-react';
import { useForm } from 'react-hook-form';
import { Link, useNavigate } from 'react-router-dom';
import { z } from 'zod';
import { api } from '../api/client';
import { ErrorState, PageHeader } from '../components/ui';

const schema = z.object({
  title: z.string().trim().min(1, 'Give the project a title').max(240),
  primary_question: z.string().trim().min(3, 'Enter a focused research question').max(5000),
  description: z.string().max(20000).optional(),
});
type FormData = z.infer<typeof schema>;

export function NewProjectPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const form = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: { title: '', primary_question: '', description: '' },
  });
  const create = useMutation({
    mutationFn: api.createProject,
    onSuccess: (project) => {
      void queryClient.invalidateQueries({ queryKey: ['projects'] });
      navigate(`/projects/${project.id}`);
    },
  });
  return (
    <div className="mx-auto max-w-3xl">
      <Link
        to="/"
        className="mb-6 inline-flex items-center gap-2 text-sm text-ink-500 hover:text-ink-950"
      >
        <ArrowLeft className="h-4 w-4" />
        All projects
      </Link>
      <PageHeader
        eyebrow="New project"
        title="Begin with the question."
        description="A clear question keeps collection and retrieval focused. You can revise it at any time without losing project history."
      />
      <form
        className="panel space-y-6"
        onSubmit={form.handleSubmit((values) => create.mutate(values))}
      >
        <div>
          <label className="label" htmlFor="title">
            Project title
          </label>
          <input
            id="title"
            className="field"
            autoFocus
            {...form.register('title')}
            aria-invalid={Boolean(form.formState.errors.title)}
          />
          {form.formState.errors.title ? (
            <p className="mt-1 text-sm text-red-700">{form.formState.errors.title.message}</p>
          ) : null}
        </div>
        <div>
          <label className="label" htmlFor="question">
            Primary research question
          </label>
          <textarea
            id="question"
            className="field min-h-32 resize-y"
            placeholder="What changed after the municipal transit pilot began?"
            {...form.register('primary_question')}
          />
          {form.formState.errors.primary_question ? (
            <p className="mt-1 text-sm text-red-700">
              {form.formState.errors.primary_question.message}
            </p>
          ) : null}
        </div>
        <div>
          <label className="label" htmlFor="description">
            Description <span className="font-normal text-ink-500">(optional)</span>
          </label>
          <textarea
            id="description"
            className="field min-h-24 resize-y"
            {...form.register('description')}
          />
        </div>
        {create.isError ? <ErrorState error={create.error} /> : null}
        <div className="flex justify-end">
          <button className="button-primary" disabled={create.isPending}>
            {create.isPending ? 'Creating…' : 'Create project'}
            <ArrowRight className="h-4 w-4" />
          </button>
        </div>
      </form>
    </div>
  );
}
