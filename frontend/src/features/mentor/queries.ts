import { useQuery } from '@tanstack/react-query';

import { api } from '../../api/endpoints';

export function useMentorStudents() {
  return useQuery({ queryKey: ['mentor', 'students'], queryFn: api.mentorStudents });
}

export function useMentorStudent(id: string) {
  return useQuery({
    queryKey: ['mentor', 'students', id],
    queryFn: () => api.mentorStudent(id),
  });
}
