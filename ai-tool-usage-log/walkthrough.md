# Walkthrough - Mini HMS Implementation Complete

We have successfully developed, tested, and deployed the Mini Hospital Management System (HMS) using Django, the Serverless Framework (`serverless-offline`), and Google Calendar integrations. The code is structured in the requested repository layout and has been pushed to the GitHub repository: `https://github.com/anshbhogal/Mini-HMS`.

---

## Directory Structure

```
Mini-HMS/
├── README.md                  <- Written report (Setup, Architecture, Decisions, Limitations)
├── requirements.txt           <- Python project dependencies (Django, Google API clients, etc.)
├── ai-tool-usage-log/         <- AI interaction transcripts
│   ├── chat_history.md        <- Raw conversation history
│   └── codex-restructure-session.md
├── hms/                       <- Django application root
│   ├── manage.py
│   ├── db.sqlite3
│   ├── hms/                   <- Django core app (models, views, templates, tests, emails)
│   │   ├── models.py          <- User roles, slots, bookings, google credentials
│   │   ├── views.py           <- Auth, dashboards, select_for_update booking locks, OAuth callbacks
│   │   ├── calendar_sync.py   <- Google Calendar integration & token refreshing
│   │   ├── emails.py          <- Asynchronous serverless email client connector
│   │   ├── templates/         <- Premium visual templates (base, signup, dashboards)
│   │   └── tests.py           <- Concurrency race condition tests
│   └── mini_hms/              <- Project settings and routing
└── email-service/             <- Serverless email function (Serverless v3 offline)
    ├── serverless.yml         <- Service triggers configurations
    ├── handler.py             <- Welcome and booking email handler
    └── package.json           <- Offline dev dependencies
```

---

## Features Implemented & Verified

### 1. Secure Booking Concurrency Lock
We wrapped the booking pipeline in a transaction atomic block using `select_for_update()` to resolve concurrent race conditions at the database level:
- Prevents double booking on the same availability slot.
- Fully verified via unit tests and automated parallel thread simulations.

### 2. Role-Based Auth & Access Control
- Custom User model implementing distinct `doctor` and `patient` roles.
- Dedicated dashboards for doctors (availability configuration, slots overview) and patients (doctor filtering, booking slots, schedule timeline).
- Access control enforced via view decorators.

### 3. Serverless Email Service Triggers
- Decoupled email function running locally with `serverless-offline` on port 3000.
- Asynchronous API invokes from Django (running in background threads).
- Supports `SIGNUP_WELCOME` and `BOOKING_CONFIRMATION` triggers.
- Writes to local `sent_emails.log` and outputs details to stdout/console.

### 4. Google Calendar OAuth2 Integration
- Dynamic connection redirects to Google consent screens.
- Auto-refreshing stored OAuth tokens dynamically when credentials expire.
- Automatically inserts scheduled events on calendars for both parties upon booking confirmation.
- Includes a local developer **Mock/Console mode** if API credentials are not supplied, allowing flawless offline runs.

---

## Verification & Test Results

We ran the Django unit tests using `python hms/manage.py test hms`. All four tests passed successfully:
1. `test_role_based_access` - Checked authorization boundaries and login redirections.
2. `test_booking_success` - Verified standard booking creation.
3. `test_cannot_book_already_booked_slot` - Confirmed slot protection.
4. `test_booking_race_condition` - Validated concurrent write protection under parallel thread conditions.

```
Creating test database for alias 'default'...
Found 4 test(s).
System check identified no issues (0 silenced).
.[Calendar Mock] Doctor drsmith Calendar Event: Title='Appointment with Mary Jane', Start=2026-06-27T07:03:26.730812+00:00, End=2026-06-27T08:03:26.730812+00:00
[Calendar Mock] Patient maryjane Calendar Event: Title='Appointment with Dr. Dr. Smith', Start=2026-06-27T07:03:26.730812+00:00, End=2026-06-27T08:03:26.730812+00:00
.[Calendar Mock] Doctor drsmith Calendar Event: Title='Appointment with John Doe', Start=2026-06-27T07:03:27.903234+00:00, End=2026-06-27T08:03:27.903234+00:00
[Calendar Mock] Patient johndoe Calendar Event: Title='Appointment with Dr. Dr. Smith', Start=2026-06-27T07:03:27.903234+00:00, End=2026-06-27T08:03:27.903234+00:00
..
----------------------------------------------------------------------
Ran 4 tests in 3.451s

OK
Destroying test database for alias 'default'...
```
