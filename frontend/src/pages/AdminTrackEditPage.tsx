import { useParams } from "react-router-dom";

import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { AdminTrackForm } from "../features/admin/AdminTrackForm";
import { useAdminTrack, useAdminTrackOptions } from "../features/admin/queries";

export function AdminTrackEditPage() {
  const { trackId = "" } = useParams();
  const track = useAdminTrack(trackId);
  const options = useAdminTrackOptions();
  if (track.isPending || options.isPending) {
    return <LoadingState label="Загружаем настройки трека…" />;
  }
  if (track.isError || options.isError) {
    return (
      <ErrorState
        error={track.error ?? options.error}
        retry={() => {
          void track.refetch();
          void options.refetch();
        }}
      />
    );
  }
  return (
    <AdminTrackForm
      key={track.data.id}
      track={track.data}
      options={options.data}
    />
  );
}
