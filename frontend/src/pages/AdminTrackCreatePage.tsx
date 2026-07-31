import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { AdminTrackForm } from "../features/admin/AdminTrackForm";
import { useAdminTrackOptions } from "../features/admin/queries";

export function AdminTrackCreatePage() {
  const options = useAdminTrackOptions();
  if (options.isPending)
    return <LoadingState label="Готовим конструктор трека…" />;
  if (options.isError)
    return <ErrorState retry={() => void options.refetch()} />;
  return <AdminTrackForm options={options.data} />;
}
