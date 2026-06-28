# Mini Hospital Management System (HMS) Implementation Plan

We are building a local-focused Django web application for doctor availability scheduling and patient appointment booking. The system includes a separate serverless email service for sending welcome and booking emails.

## User Review Required

> [!IMPORTANT]
> **PostgreSQL Configuration**: The local environment does not currently have PostgreSQL running on port 5432. We will default our configurations in `settings.py` to use a standard PostgreSQL setup. However, to make local execution and evaluation seamless, we will also implement a dynamic fallback/toggle to SQLite in Django if the `.env` specifies it, or if PostgreSQL is unreachable. This ensures the app can run immediately on a fresh machine.
>
> **Google OAuth2 Credentials**: The Google Calendar API integration requires Google Cloud OAuth2 client credentials (`Client ID` and `Client Secret`). To allow local testing without valid credentials, we will provide a **Mock/Console Mode** for Google Calendar API which logs the calendar event data to the Django log when credentials are not configured, alongside the functional OAuth2 code.

## Open Questions

1. **PostgreSQL Credentials**: Are there specific PostgreSQL credentials (username, password, database name) you would like us to configure as defaults, or should we use standard defaults (`postgres` / `password` / `mini_hms`)?
2. **Serverless Local Trigger Port**: The serverless-offline plugin runs on `http://localhost:3000` by default. Can we assume port 3000 is free for the serverless-offline service to run?

## Proposed Changes

We will divide the codebase into two main directories:
1. `backend/` - The Django project.
2. `email_service/` - The Serverless Framework service.

---

### Backend (Django)

#### [NEW] [requirements.txt](file:///d:/Mini%20HMS/backend/requirements.txt)
Python dependency file for Django, Google API Client, and database connectors:
- `django`
- `psycopg2-binary`
- `requests`
- `django-environ`
- `google-auth`
- `google-auth-oauthlib`
- `google-api-python-client`

#### [NEW] [models.py](file:///d:/Mini%20HMS/backend/hms/models.py)
Data models:
- **`User` (AbstractUser)**: Custom user model containing a `role` field (choices: `doctor`, `patient`).
- **`Availability`**: Doctor time slots.
  - Fields: `doctor` (FK to User), `start_time` (DateTime), `end_time` (DateTime), `is_booked` (Boolean).
- **`Booking`**: Appointment booking.
  - Fields: `patient` (FK to User), `doctor` (FK to User), `availability_slot` (OneToOneField to Availability to guarantee a slot can only be booked once), `created_at` (DateTime), `doctor_google_event_id` (String), `patient_google_event_id` (String).
- **`GoogleCredentials`**: Store encrypted/serialized OAuth2 credentials.
  - Fields: `user` (OneToOneField to User), `credential_data` (TextField/JSONField).

#### [NEW] [views.py](file:///d:/Mini%20HMS/backend/hms/views.py)
Logic handlers:
- **Auth Views**: Sign up, log in, logout with role-based redirection.
- **Doctor Dashboard**: Manage availability slots (create, delete, list).
- **Patient Dashboard**: List doctors, view their upcoming availability, and book slots.
- **Race Condition Booking Flow**:
  We will wrap the booking process inside a database transaction block using `select_for_update()` to lock the selected availability slot row:
  ```python
  from django.db import transaction
  
  with transaction.atomic():
      # Lock the slot for update
      slot = Availability.objects.select_for_update().get(id=slot_id)
      if slot.is_booked or slot.start_time <= timezone.now():
          raise ValidationError("Slot is no longer available.")
      
      # Mark slot as booked
      slot.is_booked = True
      slot.save()
      
      # Create booking record
      booking = Booking.objects.create(patient=patient, doctor=slot.doctor, availability_slot=slot)
  ```
- **Google OAuth2 Flow**:
  - `/google/connect/` -> Initiates the authorization flow, redirecting the user to Google's consent screen.
  - `/google/oauth2callback/` -> Handles Google's callback, exchanges the auth code for tokens, and saves them in `GoogleCredentials` for the logged-in user.
- **Calendar Event Sync logic**:
  A helper function that runs after a booking is confirmed to instantiate the Google Calendar client for both the doctor and the patient (if they have connected their accounts) and inserts the event details.

#### [NEW] [emails.py](file:///d:/Mini%20HMS/backend/hms/emails.py)
Helper functions to send trigger payloads asynchronously to the serverless-offline email notification service using background threads (`threading.Thread`).

#### [NEW] [templates/](file:///d:/Mini%20HMS/backend/hms/templates/)
Premium, visual-heavy UI templates using Inter/Outfit fonts, modern gradients, glassmorphism, responsive grids, and subtle interactive animations:
- `base.html` - Shared style rules, header/footer, and common styling.
- `index.html` - Premium landing page highlighting doctor search and booking capabilities.
- `signup.html` / `login.html` - Elegant input forms with validation.
- `doctor_dashboard.html` - Time-slot setup and booking overview.
- `patient_dashboard.html` - Doctor browser, slot selector, and active bookings.

---

### Email Service (Serverless Framework)

#### [NEW] [serverless.yml](file:///d:/Mini%20HMS/email_service/serverless.yml)
Configures the Serverless Python function using the `serverless-offline` plugin and sets up local HTTP triggers.

#### [NEW] [package.json](file:///d:/Mini%20HMS/email_service/package.json)
Contains NPM dependencies for running the local Serverless offline environment:
- `serverless`
- `serverless-offline`

#### [NEW] [handler.py](file:///d:/Mini%20HMS/email_service/handler.py)
Exposes the entry point for the Lambda function.
- Decodes the POST payload containing `trigger`, `recipient_email`, and `data`.
- Validates the trigger types (`SIGNUP_WELCOME` and `BOOKING_CONFIRMATION`).
- If SMTP credentials are set, sends a real email using Python's `smtplib`. Otherwise, falls back to printing the email contents to the terminal console and writing them to `email_service/logs/sent_emails.log` for validation.

---

## Verification Plan

### Automated Tests
- We will write Django tests in `backend/hms/tests.py` covering:
  - Role-based registration and access control (patients cannot access doctor endpoints).
  - Multi-threaded race condition booking tests where multiple threads try to book the same slot simultaneously, verifying only one succeeds and the other receives a failure.
- We will run the Django test suite using:
  `python backend/manage.py test hms`

### Manual Verification
1. **Serverless Offline Launch**: Run `npx serverless offline` in the `email_service/` directory and check that it is running.
2. **Django Launch**: Start the Django development server, register a doctor and patient, connect google accounts (or verify mock logs), create slots, and book them.
3. **Email Verification**: Confirm that signup and booking send events to the Serverless service, and verify the email logs print out correctly in the serverless terminal.
