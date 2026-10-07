import { useEffect, useRef } from "react";

import type { ProtectedContentMediaRead } from "../types/api";
import type { UploadOptions } from "../api/client";
import {
  contentImageSource,
  validateContentImage,
} from "../utils/contentImages";

interface PendingImage {
  file: File;
  previewUrl?: string;
  uploaded?: ProtectedContentMediaRead;
}

export function useContentImages() {
  const images = useRef(new Map<string, PendingImage>());
  const controller = useRef<AbortController | null>(null);
  useEffect(() => {
    const pending = images.current;
    return () => {
      controller.current?.abort();
      for (const image of pending.values()) {
        if (image.previewUrl) URL.revokeObjectURL(image.previewUrl);
      }
    };
  }, []);

  const referenced = (markdown: string) =>
    [...images.current.entries()].filter(([source]) =>
      markdown.includes(`](${source})`),
    );

  return {
    queue(file: File) {
      validateContentImage(file);
      const source = `/content-images/pending/${crypto.randomUUID()}`;
      images.current.set(source, {
        file,
        previewUrl:
          typeof URL.createObjectURL === "function"
            ? URL.createObjectURL(file)
            : undefined,
      });
      return { source, name: file.name || "Изображение" };
    },
    previews(markdown: string) {
      return referenced(markdown).map(([source, image]) => ({
        source,
        name: image.file.name,
        url: image.previewUrl,
      }));
    },
    hasPending(markdown: string) {
      return referenced(markdown).length > 0;
    },
    draftMarkdown(markdown: string) {
      return markdown.replace(
        /!\[[^\]]*\]\(\/content-images\/pending\/[0-9a-f-]+\)/gi,
        "[Изображение будет добавлено при сохранении]",
      );
    },
    async prepare(
      markdown: string,
      upload: (
        file: File,
        options: UploadOptions,
      ) => Promise<ProtectedContentMediaRead>,
    ) {
      let result = markdown;
      const uploadController = new AbortController();
      controller.current = uploadController;
      for (const [source, image] of referenced(markdown)) {
        // Keep successful uploads when a later upload or article save fails.
        image.uploaded ??= await upload(image.file, {
          signal: uploadController.signal,
        });
        result = result.replaceAll(
          source,
          contentImageSource(image.uploaded.id),
        );
      }
      return result;
    },
  };
}
