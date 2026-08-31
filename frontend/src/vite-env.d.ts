/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL?: string;
  readonly VITE_DEV_STUDENT_ID?: string;
  readonly VITE_DEV_ALUMNI_ID?: string;
  readonly VITE_DEV_MENTOR_ID?: string;
  readonly VITE_DEV_ADMIN_ID?: string;
  readonly VITE_TELEGRAM_BOT_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
