import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { AdminStudentForm } from "../features/admin/AdminStudentForm";
import { useAdminStudentOptions } from "../features/admin/studentQueries";

export function AdminStudentCreatePage() {
  const options = useAdminStudentOptions();
  if (options.isPending) {
    return <LoadingState label="Готовим форму ученика…" />;
  }
  if (options.isError) {
    return (
      <ErrorState error={options.error} retry={() => void options.refetch()} />
    );
  }
  return <AdminStudentForm options={options.data} />;
}
