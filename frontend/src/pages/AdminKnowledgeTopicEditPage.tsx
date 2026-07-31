import { useParams } from "react-router-dom";

import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { AdminKnowledgeTopicForm } from "../features/admin/AdminKnowledgeTopicForm";
import { useAdminKnowledgeTopic } from "../features/admin/knowledgeQueries";

export function AdminKnowledgeTopicEditPage() {
  const { topicId = "" } = useParams();
  const query = useAdminKnowledgeTopic(topicId);
  if (query.isPending) return <LoadingState label="Загружаем материалы…" />;
  if (query.isError) return <ErrorState retry={() => void query.refetch()} />;
  return <AdminKnowledgeTopicForm key={query.data.id} topic={query.data} />;
}
