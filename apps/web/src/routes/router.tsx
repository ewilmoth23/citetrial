import { createBrowserRouter } from 'react-router-dom';
import { LoadingState } from '../components/ui';
import { AppLayout } from '../layouts/AppLayout';
import { ProjectLayout } from '../layouts/ProjectLayout';
import { BriefPage } from '../pages/BriefPage';
import { ClaimsPage } from '../pages/ClaimsPage';
import { DashboardPage } from '../pages/DashboardPage';
import { EvidenceMatrixPage } from '../pages/EvidenceMatrixPage';
import { ExportsPage } from '../pages/ExportsPage';
import { HistoryPage } from '../pages/HistoryPage';
import { NewProjectPage } from '../pages/NewProjectPage';
import { NotesPage } from '../pages/NotesPage';
import { NotFoundPage } from '../pages/NotFoundPage';
import { ProjectOverviewPage } from '../pages/ProjectOverviewPage';
import { SearchPage } from '../pages/SearchPage';
import { SettingsPage } from '../pages/SettingsPage';
import { SourcesPage } from '../pages/SourcesPage';
import { TimelinePage } from '../pages/TimelinePage';

export const router = createBrowserRouter([
  {
    element: <AppLayout />,
    hydrateFallbackElement: <LoadingState label="Opening research workspace…" />,
    children: [
      { index: true, element: <DashboardPage /> },
      { path: 'projects/new', element: <NewProjectPage /> },
      {
        path: 'projects/:projectId',
        element: <ProjectLayout />,
        children: [
          { index: true, element: <ProjectOverviewPage /> },
          { path: 'sources', element: <SourcesPage /> },
          {
            path: 'sources/:sourceId',
            lazy: async () => {
              const { SourceDetailPage } = await import('../pages/SourceDetailPage');
              return { Component: SourceDetailPage };
            },
          },
          { path: 'search', element: <SearchPage /> },
          {
            path: 'chat',
            lazy: async () => {
              const { ChatPage } = await import('../pages/ChatPage');
              return { Component: ChatPage };
            },
          },
          { path: 'claims', element: <ClaimsPage /> },
          { path: 'evidence', element: <EvidenceMatrixPage /> },
          { path: 'timeline', element: <TimelinePage /> },
          { path: 'notes', element: <NotesPage /> },
          { path: 'brief', element: <BriefPage /> },
          { path: 'exports', element: <ExportsPage /> },
          { path: 'history', element: <HistoryPage /> },
          { path: 'settings', element: <SettingsPage /> },
        ],
      },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
]);
