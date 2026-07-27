import { expect, test, type Page, type Route } from '@playwright/test';
import path from 'node:path';

const project = {
  id: 'project-1',
  title: 'Harbor Loop investigation',
  primary_question: 'What effects did the Harbor Loop pilot have?',
  description: 'Synthetic E2E project',
  status: 'analyzing',
  created_at: '2032-01-01T00:00:00Z',
  updated_at: '2032-01-01T00:00:00Z',
  source_count: 0,
  processed_source_count: 0,
  claim_count: 0,
  disputed_claim_count: 0,
  unresolved_claim_count: 0,
  timeline_event_count: 1,
  brief_status: null,
};

const baseSource = {
  project_id: 'project-1',
  normalized_url: null,
  final_url: null,
  author: null,
  publisher: null,
  publication_date: null,
  publication_date_is_explicit: false,
  retrieved_at: null,
  content_hash: 'abc123',
  extraction_method: 'synthetic/mock',
  processing_status: 'ready',
  warnings: [],
  error_message: null,
  mime_type: 'text/html',
  http_status: 200,
  redirect_count: 0,
  category: null,
  importance: null,
  trust_note: null,
  source_label: null,
  created_at: '2032-01-01T00:00:00Z',
  updated_at: '2032-01-01T00:00:00Z',
  chunk_count: 1,
  duplicate_warnings: [],
  processing_job: null,
};

async function installMockApi(page: Page) {
  const sources: Array<Record<string, unknown>> = [];
  const claims: Array<Record<string, unknown>> = [];
  let conversations: Array<Record<string, unknown>> = [];
  let timeline = [
    {
      id: 'event-1',
      project_id: 'project-1',
      title: 'Signal tuning began',
      date_start: null,
      date_end: null,
      date_label: 'around late spring 2032',
      date_precision: 'approximate',
      description: 'The source did not name an exact day.',
      confidence: 0.7,
      origin: 'model_suggestion',
      review_status: 'suggested',
      sort_order: 0,
      created_at: '2032-01-01',
      updated_at: '2032-01-01',
      evidence: [
        {
          id: 'timeline-evidence-1',
          source_id: 'source-web',
          excerpt: 'around late spring 2032',
          location: 'Meeting note',
        },
      ],
    },
  ];
  let briefs: Array<Record<string, unknown>> = [];

  const fulfillJson = (route: Route, body: unknown, status = 200) =>
    route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const pathname = url.pathname;
    const method = request.method();
    if (pathname === '/api/v1/projects' && method === 'GET')
      return fulfillJson(route, { items: [], total: 0, limit: 50, offset: 0 });
    if (pathname === '/api/v1/projects' && method === 'POST')
      return fulfillJson(route, project, 201);
    if (pathname === '/api/v1/projects/project-1' && method === 'GET')
      return fulfillJson(route, {
        ...project,
        source_count: sources.length,
        processed_source_count: sources.length,
        claim_count: claims.length,
      });
    if (pathname.endsWith('/history'))
      return fulfillJson(route, [
        {
          id: 'activity-1',
          action: 'project_created',
          detail: project.title,
          created_at: '2032-01-01T00:00:00Z',
        },
      ]);
    if (pathname.endsWith('/sources') && method === 'GET')
      return fulfillJson(route, { items: sources, total: sources.length, limit: 100, offset: 0 });
    if (pathname.endsWith('/sources/web') && method === 'POST') {
      const source = {
        ...baseSource,
        id: 'source-web',
        source_type: 'webpage',
        original_name: 'https://example.org/transit',
        normalized_url: 'https://example.org/transit',
        final_url: 'https://example.org/transit',
        title: 'Synthetic transit article',
      };
      sources.push(source);
      return fulfillJson(route, source, 202);
    }
    if (pathname.endsWith('/sources/upload') && method === 'POST') {
      const source = {
        ...baseSource,
        id: 'source-pdf',
        source_type: 'pdf',
        original_name: 'transit-evaluation-report.pdf',
        title: 'Transit evaluation report',
        mime_type: 'application/pdf',
      };
      sources.push(source);
      return fulfillJson(route, source, 202);
    }
    if (pathname.endsWith('/search') && method === 'POST')
      return fulfillJson(route, {
        query: 'boardings',
        warnings: [],
        results: [
          {
            chunk_id: 'chunk-1',
            source_id: 'source-web',
            source_title: 'Synthetic transit article',
            source_type: 'webpage',
            location: {
              page_number: null,
              heading_path: 'Ridership',
              line_start: null,
              line_end: null,
            },
            excerpt: 'Weekday boardings increased from 6,800 to 8,240 in September.',
            score: 0.9,
            method: 'hybrid',
          },
        ],
      });
    if (pathname.endsWith('/conversations') && method === 'GET')
      return fulfillJson(route, conversations);
    if (pathname.endsWith('/conversations') && method === 'POST') {
      const conversation = {
        id: 'conversation-1',
        project_id: 'project-1',
        title: 'Research conversation',
        selected_source_ids: [],
        created_at: '2032-01-01',
        updated_at: '2032-01-01',
        messages: [],
      };
      conversations = [conversation];
      return fulfillJson(route, conversation, 201);
    }
    if (pathname.endsWith('/conversations/conversation-1/messages') && method === 'POST') {
      const citation = {
        id: 'citation-1',
        source_id: 'source-web',
        source_chunk_id: 'chunk-1',
        marker: '[Source 1, “Ridership”]',
        excerpt: 'Weekday boardings increased from 6,800 to 8,240 in September.',
        location: 'Ridership',
        source_title: 'Synthetic transit article',
      };
      const response = {
        user_message: {
          id: 'message-user',
          role: 'user',
          content: 'What changed?',
          generated: false,
          warning: null,
          created_at: '2032-01-01',
          citations: [],
        },
        answer_message: {
          id: 'message-answer',
          role: 'assistant',
          content: 'Stored records report an increase. [Source 1]',
          generated: true,
          warning: null,
          created_at: '2032-01-01',
          citations: [citation],
        },
        retrieved: [],
        provider_available: true,
      };
      conversations[0] = {
        ...conversations[0],
        messages: [response.user_message, response.answer_message],
      };
      return fulfillJson(route, response);
    }
    if (pathname.endsWith('/claims') && method === 'GET') return fulfillJson(route, claims);
    if (pathname.endsWith('/claims') && method === 'POST') {
      const body = request.postDataJSON();
      const claim = {
        id: 'claim-1',
        project_id: 'project-1',
        ...body,
        confidence: null,
        user_notes: null,
        created_at: '2032-01-01',
        updated_at: '2032-01-01',
        evidence: [],
      };
      claims.push(claim);
      return fulfillJson(route, claim, 201);
    }
    if (pathname.endsWith('/claims/claim-1/evidence') && method === 'POST') {
      const body = request.postDataJSON();
      const evidence = {
        id: `evidence-${(claims[0].evidence as unknown[]).length + 1}`,
        claim_id: 'claim-1',
        ...body,
        source_chunk_id: null,
        confidence: null,
        notes: null,
        created_at: '2032-01-01',
        source_title: 'Synthetic transit article',
      };
      (claims[0].evidence as unknown[]).push(evidence);
      return fulfillJson(route, evidence, 201);
    }
    if (pathname.endsWith('/timeline') && method === 'GET') return fulfillJson(route, timeline);
    if (pathname.endsWith('/timeline/event-1') && method === 'PATCH') {
      timeline = [{ ...timeline[0], review_status: 'accepted' }];
      return fulfillJson(route, timeline[0]);
    }
    if (pathname.endsWith('/briefs') && method === 'GET') return fulfillJson(route, briefs);
    if (pathname.endsWith('/briefs') && method === 'POST') {
      const brief = {
        id: 'brief-1',
        project_id: 'project-1',
        title: 'Research brief',
        status: 'draft',
        created_at: '2032-01-01',
        updated_at: '2032-01-01',
        sections: [
          {
            id: 'section-1',
            section_type: 'executive_summary',
            title: 'Executive summary',
            content: '',
            ordinal: 0,
            origin: 'generated',
            user_edited: false,
            generation_warning: null,
            updated_at: '2032-01-01',
          },
        ],
      };
      briefs = [brief];
      return fulfillJson(route, brief, 201);
    }
    if (pathname.includes('/sections/section-1/generate') && method === 'POST') {
      const section = {
        ...(briefs[0].sections as Record<string, unknown>[])[0],
        content: 'Evidence-backed generated summary. [Source 1]',
      };
      (briefs[0].sections as Record<string, unknown>[])[0] = section;
      return fulfillJson(route, section);
    }
    if (pathname.includes('/sections/section-1') && method === 'PATCH') {
      const section = {
        ...(briefs[0].sections as Record<string, unknown>[])[0],
        ...request.postDataJSON(),
        origin: 'user',
        user_edited: true,
      };
      (briefs[0].sections as Record<string, unknown>[])[0] = section;
      return fulfillJson(route, section);
    }
    if (pathname.endsWith('/exports/markdown'))
      return route.fulfill({
        status: 200,
        contentType: 'text/markdown',
        headers: { 'Content-Disposition': 'attachment; filename="citetrail.md"' },
        body: '# Harbor Loop investigation\n\n[Source 1]',
      });
    if (pathname === '/api/v1/settings')
      return fulfillJson(route, {
        data_dir: '/data',
        model_provider: 'mock',
        model_name: 'mock',
        provider_requests_leave_device: false,
      });
    if (pathname === '/api/v1/health') return fulfillJson(route, { status: 'healthy' });
    if (pathname === '/api/v1/projects/project-1' && method === 'DELETE')
      return route.fulfill({ status: 204 });
    return fulfillJson(route, {});
  });
}

test('complete deterministic research workflow', async ({ page }) => {
  await installMockApi(page);
  await page.goto('/');
  await page.getByRole('link', { name: 'Start a project' }).click();
  await page.getByLabel('Project title').fill('Harbor Loop investigation');
  await page
    .getByLabel('Primary research question')
    .fill('What effects did the Harbor Loop pilot have?');
  await page.getByRole('button', { name: 'Create project' }).click();
  await expect(page.getByRole('heading', { name: 'Harbor Loop investigation' })).toBeVisible();

  await page.getByRole('link', { name: 'Sources', exact: true }).click();
  await page.getByRole('button', { name: 'Webpage' }).click();
  await page.getByLabel('HTTPS URL').fill('https://example.org/transit');
  await page.getByRole('button', { name: 'Add webpage' }).click();
  await expect(page.getByText('Synthetic transit article')).toBeVisible();
  await page.getByRole('button', { name: 'Upload' }).click();
  await page
    .getByLabel('PDF, Markdown, or text file')
    .setInputFiles(path.resolve('../../sample_data/transit-evaluation-report.pdf'));
  await page.getByRole('button', { name: 'Upload and process' }).click();
  await expect(page.getByText('Transit evaluation report')).toBeVisible();

  await page.getByRole('link', { name: 'Search', exact: true }).click();
  await page.getByPlaceholder(/Search for a claim/).fill('boardings');
  await page.getByRole('button', { name: 'Search sources' }).click();
  await expect(page.getByText(/6,800 to 8,240/)).toBeVisible();

  await page.getByRole('link', { name: 'Research chat', exact: true }).click();
  await page.getByLabel('Question').fill('What changed?');
  await page.getByRole('button', { name: 'Ask' }).click();
  await expect(page.getByText(/Stored records report an increase/)).toBeVisible();
  await expect(
    page.getByRole('link', { name: /Source 1.*Synthetic transit article/ }),
  ).toBeVisible();

  await page.getByRole('link', { name: 'Claims', exact: true }).click();
  await page.getByRole('button', { name: 'New claim' }).click();
  await page
    .getByLabel('Claim or unresolved question')
    .fill('September boarding totals increased.');
  await page.getByRole('button', { name: 'Create proposed claim' }).click();
  await page.getByRole('button', { name: 'Link evidence' }).click();
  await page.getByLabel('Stored source').selectOption('source-web');
  await page
    .getByLabel('Exact excerpt')
    .fill('Weekday boardings increased from 6,800 to 8,240 in September.');
  await page.getByRole('button', { name: 'Verify and link' }).click();
  await page.getByRole('button', { name: 'Link evidence' }).click();
  await page.getByLabel('Stored source').selectOption('source-web');
  await page.getByLabel('Relationship').selectOption('contradicts');
  await page.getByLabel('Exact excerpt').fill('A second synthetic calculation reported 7,510.');
  await page.getByRole('button', { name: 'Verify and link' }).click();

  await page.getByRole('link', { name: 'Timeline', exact: true }).click();
  await expect(page.getByText(/around late spring 2032 · approximate/)).toBeVisible();
  await page.getByRole('button', { name: 'Accept' }).click();

  await page.getByRole('link', { name: 'Brief builder', exact: true }).click();
  await page.getByRole('button', { name: 'Create brief' }).click();
  await page.getByRole('button', { name: 'Generate section' }).click();
  const editor = page.getByLabel('Executive summary content');
  await expect(editor).toHaveValue(/Evidence-backed/);
  await editor.fill('Reviewed, user-edited summary. [Source 1]');
  await page.getByRole('button', { name: 'Save' }).click();

  await page.getByRole('link', { name: 'Exports', exact: true }).click();
  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('link', { name: 'Download Markdown' }).click();
  expect((await downloadPromise).suggestedFilename()).toContain('markdown');

  await page.getByRole('link', { name: 'Settings', exact: true }).click();
  page.on('dialog', async (dialog) => dialog.accept('DELETE'));
  await page.getByRole('button', { name: 'Delete project' }).click();
  await expect(page).toHaveURL('/');
});
