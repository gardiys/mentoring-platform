# Russian Trusted CA for Tochka API

Tochka Bank documents that `https://enter.tochka.com/uapi` uses the national
Russian Trusted CA chain, which is not included in the default Python/certifi
bundle. The backend image installs these two PEM certificates into its Debian
system bundle and only the Tochka HTTP client is explicitly pointed at that
bundle.

Official sources:

- https://gu-st.ru/content/lending/russian_trusted_root_ca_pem.crt
- https://gu-st.ru/content/lending/russian_trusted_sub_ca_pem.crt
- https://developers.tochka.com/docs/tochka-api/certificate

Verified on 2026-08-25:

- Root SHA-256 fingerprint: `D2:6D:2D:02:31:B7:C3:9F:92:CC:73:85:12:BA:54:10:35:19:E4:40:5D:68:B5:BD:70:3E:97:88:CA:8E:CF:31`
- Sub CA SHA-256 fingerprint: `BB:BD:E2:10:3E:79:0B:99:9E:C6:2B:D0:3C:F6:25:A5:A2:E7:C3:16:E1:0A:FE:6A:49:0E:ED:EA:D8:B3:FD:9B`
- Root expires: 2032-02-27
- Sub CA expires: 2027-03-06; replace it from the official source before expiry.
