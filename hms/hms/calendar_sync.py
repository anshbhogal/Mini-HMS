import google.auth.transport.requests
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from django.conf import settings
from .models import GoogleCredentials

def get_google_service(user):
    """
    Instantiates a Google Calendar API service instance for the given user if they have saved credentials.
    Handles token refreshing if expired.
    """
    try:
        cred_obj = GoogleCredentials.objects.get(user=user)
        cred_dict = cred_obj.to_dict()
        
        # Prefer client settings, fallback to DB if empty
        client_id = settings.GOOGLE_CLIENT_ID or cred_dict.get('client_id')
        client_secret = settings.GOOGLE_CLIENT_SECRET or cred_dict.get('client_secret')
        
        if not client_id or not client_secret:
            return None
            
        credentials = Credentials(
            token=cred_dict['token'],
            refresh_token=cred_dict['refresh_token'],
            token_uri=cred_dict['token_uri'],
            client_id=client_id,
            client_secret=client_secret,
            scopes=cred_dict['scopes']
        )
        
        # Auto-refresh credentials if expired and refresh token is available
        if credentials.expired and credentials.refresh_token:
            request = google.auth.transport.requests.Request()
            credentials.refresh(request)
            # Update values in the model
            cred_obj.token = credentials.token
            cred_obj.save()
            
        return build('calendar', 'v3', credentials=credentials)
    except GoogleCredentials.DoesNotExist:
        return None
    except Exception as e:
        print(f"[Calendar Sync Error] Failed to configure Google Calendar service for {user.username}: {str(e)}")
        return None

def create_calendar_events(booking):
    """
    Creates appointment calendar events for both doctor and patient if they have Google accounts connected.
    If no credentials are saved, it prints event details in a Mock format.
    """
    doctor = booking.doctor
    patient = booking.patient
    slot = booking.availability_slot
    
    start_time_iso = slot.start_time.isoformat()
    end_time_iso = slot.end_time.isoformat()
    
    # 1. Setup Doctor Calendar Event
    doctor_service = get_google_service(doctor)
    if doctor_service:
        try:
            event = {
                'summary': f'Appointment with {patient.full_name or patient.username}',
                'description': 'Appointment booked via Mini Hospital Management System.',
                'start': {
                    'dateTime': start_time_iso,
                    'timeZone': 'UTC',
                },
                'end': {
                    'dateTime': end_time_iso,
                    'timeZone': 'UTC',
                },
            }
            created_event = doctor_service.events().insert(calendarId='primary', body=event).execute()
            booking.doctor_google_event_id = created_event.get('id')
            print(f"[Calendar Sync SUCCESS] Created event on Doctor {doctor.username} calendar. Event ID: {booking.doctor_google_event_id}")
        except Exception as e:
            print(f"[Calendar Sync ERROR] Failed to create event on Doctor {doctor.username} calendar: {str(e)}")
    else:
        booking.doctor_google_event_id = f"mock-doc-event-{booking.id}"
        print(f"[Calendar Mock] Doctor {doctor.username} Calendar Event: Title='Appointment with {patient.full_name or patient.username}', Start={start_time_iso}, End={end_time_iso}")
        
    # 2. Setup Patient Calendar Event
    patient_service = get_google_service(patient)
    if patient_service:
        try:
            event = {
                'summary': f'Appointment with {doctor.get_display_name()}',
                'description': 'Appointment booked via Mini Hospital Management System.',
                'start': {
                    'dateTime': start_time_iso,
                    'timeZone': 'UTC',
                },
                'end': {
                    'dateTime': end_time_iso,
                    'timeZone': 'UTC',
                },
            }
            created_event = patient_service.events().insert(calendarId='primary', body=event).execute()
            booking.patient_google_event_id = created_event.get('id')
            print(f"[Calendar Sync SUCCESS] Created event on Patient {patient.username} calendar. Event ID: {booking.patient_google_event_id}")
        except Exception as e:
            print(f"[Calendar Sync ERROR] Failed to create event on Patient {patient.username} calendar: {str(e)}")
    else:
        booking.patient_google_event_id = f"mock-pat-event-{booking.id}"
        print(f"[Calendar Mock] Patient {patient.username} Calendar Event: Title='Appointment with {doctor.get_display_name()}', Start={start_time_iso}, End={end_time_iso}")
        
    booking.save()
