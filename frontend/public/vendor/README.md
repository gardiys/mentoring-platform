# Telegram Web App SDK

`telegram-web-app-2026-07-14.js` was downloaded from
`https://telegram.org/js/telegram-web-app.js` on 2026-08-05 and pinned in the
repository. The original downloaded bytes had the following provenance:

- Upstream `Last-Modified`: `Tue, 14 Jul 2026 09:31:36 GMT`
- Original downloaded SHA-256: `113b5c9cba75dc07a92355a09973ff8a23431864e59bd7e375e21af61dbbfef6`

The repository copy was mechanically reformatted by Prettier on 2026-08-11 in
commit `fb0fa654`. It is therefore not byte-for-byte identical to the upstream
response, although no intentional functional changes were made during that
formatting pass.

- Current repository SHA-256: `cbdb82c293e40edc90f8727d0d31fff81f0b847df4ae61e80dd268721e29b11e`

`tests/vendor-telegram-sdk.test.ts` verifies the current repository hash. The
whole `public/vendor/` directory is excluded from Prettier so formatting cannot
silently change the pinned SDK again.

The application loads this classic script only for a detected Telegram Mini
App launch. Keep the filename versioned and update the hash and provenance when
reviewing a newer upstream SDK; never replace the file in place because it is
served with an immutable cache policy.
