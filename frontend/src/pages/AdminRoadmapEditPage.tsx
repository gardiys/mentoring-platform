import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { useAdminRoadmap } from "../features/admin/queries";
import type { AdminRoadmapRead, AdminRoadmapUpdate } from "../types/api";
import { AdminRoadmapCreatePage } from "./AdminRoadmapCreatePage";
import { useParams } from "react-router-dom";

function toUpdatePayload(roadmap: AdminRoadmapRead): AdminRoadmapUpdate {
  return {
    slug: roadmap.slug,
    title: roadmap.title,
    description: roadmap.description,
    position: roadmap.position,
    is_published: roadmap.is_published,
    sections: roadmap.sections.map((section) => ({
      id: section.id,
      title: section.title,
      description: section.description,
      position: section.position,
      duration_days: section.duration_days,
      topics: section.topics.map((topic) => ({
        id: topic.id,
        slug: topic.slug,
        title: topic.title,
        description: topic.description,
        content_markdown: topic.content_markdown,
        position: topic.position,
        estimated_minutes: topic.estimated_minutes,
        is_published: topic.is_published,
      })),
    })),
  };
}

export function AdminRoadmapEditPage() {
  const { roadmapId = "" } = useParams();
  const query = useAdminRoadmap(roadmapId);
  if (query.isPending) return <LoadingState label="Загружаем редактор…" />;
  if (query.isError) return <ErrorState retry={() => void query.refetch()} />;

  return (
    <AdminRoadmapCreatePage
      key={query.data.id}
      roadmapId={query.data.id}
      initialValue={toUpdatePayload(query.data)}
    />
  );
}
