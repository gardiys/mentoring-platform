import { useParams } from "react-router-dom";

import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { AdminInterviewDeckForm } from "../features/admin/AdminInterviewDeckForm";
import { useAdminInterviewDeck } from "../features/admin/interviewQueries";

export function AdminInterviewDeckEditPage() {
  const { deckId = "" } = useParams();
  const query = useAdminInterviewDeck(deckId);
  if (query.isPending) return <LoadingState label="Загружаем колоду…" />;
  if (query.isError) return <ErrorState retry={() => void query.refetch()} />;
  return <AdminInterviewDeckForm deck={query.data} />;
}
