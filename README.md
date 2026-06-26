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

### The Problem: Handling Concurrent Booking Race Conditions
In a hospital scheduling system, doctor time slots are a "hot resource." If two patients concurrently attempt to book the exact same open availability slot (e.g., June 30th at 10:00 AM), we must guarantee that exactly one booking succeeds, while the other is rejected. Allowing a double booking is a critical failure. We had to choose how to handle this race condition.

### The Alternatives Considered

#### Option 1: Optimistic Concurrency Control (OCC)
In this approach, we would add a version number or tracking timestamp field to the `Availability` slot model. When attempting to book, the application reads the slot, checks that it is free, and attempts to save it while executing an update query:
```sql
UPDATE hms_availability SET is_booked = true, version = version + 1 
WHERE id = :slot_id AND version = :read_version AND is_booked = false;
```
If the query updates 0 rows, it means another thread updated the slot in the interim, and we reject or retry the booking.
*   **Pros**: Highly performant under low conflict levels because it does not lock the database row, avoiding connection blocks.
*   **Cons**: Shifts retry complexity to the application layer. Under high conflict (e.g., many patients trying to book a popular slot when it opens), it leads to transaction collisions, high rejection rates, and CPU cycles spent on retries.

#### Option 2: Pessimistic Concurrency Control (PCC) via Database Row-Level Locking
In this approach, when a booking request is received, Django opens an atomic database transaction block and queries the slot using `select_for_update()`:
```python
with transaction.atomic():
    slot = Availability.objects.select_for_update().get(id=slot_id)
    if slot.is_booked:
        raise ValidationError("Slot already booked.")
    slot.is_booked = True
    slot.save()
    Booking.objects.create(...)
```
This forces the database engine to acquire an exclusive write lock on that specific slot row immediately. Any other concurrent query attempting to select or update that row is forced to block (wait) until the locking transaction either commits or rolls back.

### The Choice & Defense: Pessimistic Row-Level Locking
We chose **Pessimistic Row-Level Locking (Option 2)**. 

In doctor scheduling, slot conflicts are highly concentrated: multiple patients typically compete for the same popular appointment times simultaneously. 
*   Pessimistic locking acts as a traffic controller at the database engine level. By blocking the second transaction at the query stage, we eliminate the risk of dirty reads or writing phantom entries.
*   Unlike OCC, which forces the backend server to process duplicate requests only to reject them at the commit stage (and then execute complex retry loops), pessimistic locking queues concurrent requests naturally. The moment the first transaction commits, the queued transaction wakes up, immediately reads the updated `is_booked = True` state, and fails instantly without executing further logic or database writes.
*   This design ensures maximum transaction safety and data integrity, leveraging PostgreSQL's row-level locking capabilities.


## Limitations

The current configuration is development-first. `DEBUG=True`, permissive hosts, and the fallback secret key must not be used in production. I would fix deployment configuration first because a working app with weak settings is still unsafe to expose.

Google OAuth tokens and client secrets are stored as plaintext database fields. In production, these should be encrypted at rest and rotated safely. This is the next most important fix because Calendar integration handles long-lived credentials.

Email dispatch from Django uses background threads to avoid blocking the response. That is acceptable for a local demo but unreliable under real process restarts or multi-worker deployment. I would replace it with a durable queue or direct serverless invocation with retries.

The booking concurrency test passes locally, but SQLite does not behave exactly like PostgreSQL for row locks. Production should use PostgreSQL and rerun concurrency tests against the same database engine that will serve users.

The app has no cancellation, rescheduling, doctor approval, audit trail, or admin model registration. Those features would be necessary before real clinical use.
