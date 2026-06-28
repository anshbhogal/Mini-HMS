# Google OAuth and SMTP Email Configuration & Fixes Session

## User Requests
1. Integrated Google Calendar credentials into the `.env` file.
2. Debugged Google OAuth error: `InsecureTransportError: OAuth 2 MUST utilize https.`
3. Debugged Google OAuth error: `InvalidGrantError: Missing code verifier.`
4. Configured SMTP server credentials to enable real email notifications via the serverless service.
5. Debugged Serverless Offline error on Windows: `can't open file 'D:\\Mini': [Errno 2] No such file or directory` (caused by folder spaces).

## Actions Performed
1. **Google OAuth Insecure Transport**: Modified [settings.py](file:///d:/Mini%20HMS/hms/mini_hms/settings.py) to set the environment variable `OAUTHLIB_INSECURE_TRANSPORT = '1'` when `DEBUG` is active. This allows local HTTP testing.
2. **Google OAuth PKCE State Bug**: Modified `google_connect` and `google_oauth_callback` in [views.py](file:///d:/Mini%20HMS/hms/hms/views.py) to persist `flow.code_verifier` in the Django session during initial redirect and restore it in the callback flow. This prevents `Missing code verifier` errors.
3. **SMTP Credentials Setup**: Populated Gmail SMTP environment variables (`EMAIL_SMTP_HOST`, `EMAIL_SMTP_PORT`, `EMAIL_SMTP_USER`, `EMAIL_SMTP_PASSWORD`, `EMAIL_FROM`) inside both the root [.env](file:///d:/Mini%20HMS/.env) and [email-service/.env](file:///d:/Mini%20HMS/email-service/.env) files.
4. **Serverless Offline Windows Path Fix**: Directly modified the `spawn` arguments inside `node_modules/serverless-offline/src/lambda/handler-runner/python-runner/PythonRunner.js` to wrap the helper file script path (`invokePath`) and target path (`relativePath`) in double quotes, ensuring the service runs seamlessly on Windows directories containing spaces.
5. **Testing**: Executed Django test suite successfully and verified that the system works end-to-end under concurrent booking attempts, and connects live accounts.
