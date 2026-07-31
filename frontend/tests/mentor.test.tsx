import { screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';

import { api } from '../src/api/endpoints';
import { MentorStudentsPage } from '../src/pages/MentorStudentsPage';
import { renderPage } from './render';

afterEach(() => vi.restoreAllMocks());

it('MentorStudentsPage отображает учеников', async () => {
  vi.spyOn(api, 'mentorStudents').mockResolvedValue([
    {
      id: 'u1',
      first_name: 'Иван',
      last_name: 'Иванов',
      email: 'student@example.com',
      roadmaps: [],
      last_progress_at: null,
    },
  ]);
  renderPage(<MentorStudentsPage />);
  expect(await screen.findByText('Иван Иванов')).toBeInTheDocument();
});
