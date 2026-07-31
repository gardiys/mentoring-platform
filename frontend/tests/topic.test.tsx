import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';

import { api } from '../src/api/endpoints';
import { TopicPage } from '../src/pages/TopicPage';
import type { TopicDetail } from '../src/types/api';
import { renderPage } from './render';

const topic: TopicDetail = {
  id: 't1',
  slug: 'types',
  title: 'Типы данных',
  description: null,
  content_markdown: '# Материал',
  estimated_minutes: 10,
  roadmap: { id: 'r1', slug: 'python-backend', title: 'Python Backend' },
  section: { id: 's1', title: 'Основы' },
  status: 'not_started',
  started_at: null,
  first_completed_at: null,
  last_completed_at: null,
};

afterEach(() => vi.restoreAllMocks());

it('открывает ссылки из материала в новой вкладке', async () => {
  vi.spyOn(api, 'topic').mockResolvedValue({
    ...topic,
    content_markdown: '[Открыть учебный материал](https://example.com/lesson)',
  });

  renderPage(<TopicPage />, '/topics/t1', '/topics/:topicId');

  const link = await screen.findByRole('link', { name: 'Открыть учебный материал' });
  expect(link).toHaveAttribute('href', 'https://example.com/lesson');
  expect(link).toHaveAttribute('target', '_blank');
  expect(link).toHaveAttribute('rel', 'noopener noreferrer');
});

it('отправляет завершение и обновляет интерфейс', async () => {
  let completed = false;
  vi.spyOn(api, 'topic').mockImplementation(async () => ({
    ...topic,
    status: completed ? 'completed' : 'not_started',
    first_completed_at: completed ? '2026-07-31T10:00:00Z' : null,
    last_completed_at: completed ? '2026-07-31T10:00:00Z' : null,
  }));
  const mutation = vi.spyOn(api, 'updateProgress').mockImplementation(async () => {
    completed = true;
    return {
      topic_progress: {
        topic_id: 't1',
        status: 'completed',
        started_at: '2026-07-31T10:00:00Z',
        first_completed_at: '2026-07-31T10:00:00Z',
        last_completed_at: '2026-07-31T10:00:00Z',
      },
      roadmap_progress: { completed_topics: 1, total_topics: 1, progress_percent: 100 },
    };
  });

  renderPage(<TopicPage />, '/topics/t1', '/topics/:topicId');
  await userEvent.click(await screen.findByRole('button', { name: 'Отметить пройденной' }));

  expect(mutation).toHaveBeenCalledWith('t1', 'completed');
  expect(await screen.findByRole('button', { name: 'Снять отметку' })).toBeInTheDocument();
});
