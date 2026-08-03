import { useParams } from "react-router-dom";

import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { AdminStudentForm } from "../features/admin/AdminStudentForm";
import {
  useAdminStudent,
  useAdminStudentOptions,
} from "../features/admin/studentQueries";

export function AdminStudentEditPage() {
  const { studentId = "" } = useParams();
  const student = useAdminStudent(studentId);
  const options = useAdminStudentOptions();

  if (student.isPending || options.isPending) {
    return <LoadingState label="Загружаем данные ученика…" />;
  }
  if (student.isError || options.isError) {
    return (
      <ErrorState
        error={student.error ?? options.error}
        retry={() => {
          void student.refetch();
          void options.refetch();
        }}
      />
    );
  }
  return (
    <AdminStudentForm
      key={student.data.id}
      student={student.data}
      options={options.data}
    />
  );
}
