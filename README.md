## Setup and Run

1. Install Python 3.12 and Node.js 20 or newer.
2. From the repository root, create and activate a virtual environment:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

3. Install the Django dependencies:

   ```powershell
   pip install -r requirements.txt
   ```

4. Create a `.env` file in the repository root. For the quickest local run, use SQLite and console email logging:

   ```env
   DEBUG=True
   DB_ENGINE=sqlite
   EMAIL_SERVICE_URL=http://localhost:3000/dev/send-email
   GOOGLE_CLIENT_ID=
   GOOGLE_CLIENT_SECRET=
   GOOGLE_REDIRECT_URI=http://127.0.0.1:8000/google/oauth2callback/
   ```

5. In one terminal, start the serverless email service:

   ```powershell
   cd email-service
   npm install
   npm run start
   ```

   The email service runs at `http://localhost:3000/dev/send-email`. With the default `EMAIL_SMTP_HOST=console`, emails are logged to the console and to `email-service/logs/sent_emails.log`.

6. In a second terminal, run the Django database setup and start the app:

   ```powershell
   .\.venv\Scripts\Activate.ps1
   cd hms
   python manage.py migrate
   python manage.py runserver 8000
   ```

7. Open `http://127.0.0.1:8000/`. Register one doctor and one patient. The doctor can create availability slots, and the patient can book open slots.

## System Architecture

The system has two local services. The Django app in `hms/` owns users, roles, availability slots, bookings, pages, and Google Calendar integration. The serverless email function in `email-service/` owns notification formatting and delivery. Django calls the email service over HTTP using `EMAIL_SERVICE_URL`, so signup and booking events remain decoupled from the email transport.

The data model is intentionally small. `User` extends Django's `AbstractUser` with a `role` field for `doctor` or `patient` and a `full_name`. `Availability` stores doctor-owned time windows and whether each slot is booked. `Booking` links one patient, one doctor, and one availability slot through a one-to-one slot relationship, which prevents more than one booking record per slot. `GoogleCredentials` stores one OAuth credential set per user for Calendar access.

Role-based access is enforced in the Django views with `login_required` plus custom `doctor_required` and `patient_required` decorators. Doctors can create availability and view their bookings. Patients can browse doctors, view future unbooked slots, and book appointments. The booking view wraps slot reservation in `transaction.atomic()` and uses `select_for_update()` so concurrent booking attempts operate on a locked slot row.

Google Calendar integration is structured as an optional user connection. The connect view either starts a real Google OAuth flow when client credentials are configured or creates mock credentials for local testing. After a booking succeeds, `create_calendar_events()` attempts to create calendar events for both doctor and patient if credentials exist. If credentials are unavailable or local mock mode is used, the system records mock event IDs and logs the intended event.

## The Design Decision

The hard call was whether email should be sent directly inside the Django app or through a separate serverless function.

Option one was direct Django SMTP. It would be simpler to code and easier to debug because everything would live in one process. The downside is that the web request layer would know too much about email transport, and swapping from console logs to SMTP or a cloud provider would affect the Django app.

Option two was a separate serverless email service. This adds a second process during local development, but it matches the required architecture and keeps notification delivery isolated behind an HTTP boundary.

I chose the separate serverless email service. For this project, that is the better tradeoff because the Django app only needs to emit notification events, while the email service can decide whether to log, use SMTP, or later move to a provider such as SES. The boundary is small, testable, and realistic for production evolution.

## Limitations

The current configuration is development-first. `DEBUG=True`, permissive hosts, and the fallback secret key must not be used in production. I would fix deployment configuration first because a working app with weak settings is still unsafe to expose.

Google OAuth tokens and client secrets are stored as plaintext database fields. In production, these should be encrypted at rest and rotated safely. This is the next most important fix because Calendar integration handles long-lived credentials.

Email dispatch from Django uses background threads to avoid blocking the response. That is acceptable for a local demo but unreliable under real process restarts or multi-worker deployment. I would replace it with a durable queue or direct serverless invocation with retries.

The booking concurrency test passes locally, but SQLite does not behave exactly like PostgreSQL for row locks. Production should use PostgreSQL and rerun concurrency tests against the same database engine that will serve users.

The app has no cancellation, rescheduling, doctor approval, audit trail, or admin model registration. Those features would be necessary before real clinical use.
