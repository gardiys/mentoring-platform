import { useQuery } from "@tanstack/react-query";
import { useRef, useState } from "react";
import ReactMarkdown from "react-markdown";

import { resolveApiUrl } from "../api/client";
import type {
  ContentMediaPlayback,
  ProtectedContentMediaRead,
} from "../types/api";
import { contentImageId } from "../utils/contentImages";

interface Props {
  children: string;
  media: ProtectedContentMediaRead[];
  resourceKey: string;
  loadPlayback: (mediaId: string) => Promise<ContentMediaPlayback>;
  openLinksInNewTab?: boolean;
}

function ContentImage({
  id,
  alt,
  title,
  resourceKey,
  loadPlayback,
}: {
  id: string;
  alt?: string;
  title?: string;
  resourceKey: string;
  loadPlayback: Props["loadPlayback"];
}) {
  const playback = useQuery({
    queryKey: ["content-media", "playback", resourceKey, id],
    queryFn: () => loadPlayback(id),
    retry: false,
    refetchOnWindowFocus: false,
    staleTime: 0,
  });
  const retried = useRef(false);
  const [failed, setFailed] = useState(false);
  const [version, setVersion] = useState(0);
  const retry = async () => {
    const result = await playback.refetch();
    if (result.data && !result.isError) {
      setFailed(false);
      setVersion((current) => current + 1);
    } else setFailed(true);
  };
  if (playback.isPending)
    return <span role="status">Загружаем изображение…</span>;
  if (playback.isError || failed)
    return (
      <span role="alert">
        Не удалось загрузить изображение.{" "}
        <button
          type="button"
          disabled={playback.isFetching}
          onClick={() => {
            retried.current = false;
            void retry();
          }}
        >
          Повторить
        </button>
      </span>
    );
  return (
    <img
      key={version}
      src={resolveApiUrl(playback.data.url)}
      alt={alt ?? ""}
      title={title}
      loading="lazy"
      decoding="async"
      referrerPolicy="no-referrer"
      onError={() => {
        if (retried.current) setFailed(true);
        else {
          retried.current = true;
          void retry();
        }
      }}
    />
  );
}

export function ContentMarkdown({
  children,
  media,
  resourceKey,
  loadPlayback,
  openLinksInNewTab,
}: Props) {
  return (
    <ReactMarkdown
      components={{
        img: ({ src, alt, title }) => {
          const id = contentImageId(typeof src === "string" ? src : "");
          if (id) {
            if (
              !media.some(
                (item) =>
                  item.id.toLowerCase() === id.toLowerCase() &&
                  item.kind === "image",
              )
            ) {
              return <span role="alert">Изображение недоступно</span>;
            }
            return (
              <ContentImage
                id={id}
                alt={alt}
                title={title}
                resourceKey={resourceKey}
                loadPlayback={loadPlayback}
              />
            );
          }
          return src ? (
            <img
              src={src}
              alt={alt ?? ""}
              title={title}
              loading="lazy"
              decoding="async"
            />
          ) : (
            <span>{alt}</span>
          );
        },
        ...(openLinksInNewTab
          ? {
              a: ({
                children: linkChildren,
                href,
                title,
              }: {
                children?: React.ReactNode;
                href?: string;
                title?: string;
              }) => (
                <a
                  href={href}
                  title={title}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  {linkChildren}
                </a>
              ),
            }
          : {}),
      }}
    >
      {children}
    </ReactMarkdown>
  );
}
