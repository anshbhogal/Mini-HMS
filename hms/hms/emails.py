import threading
import requests
from django.conf import settings

def _send_email_async(trigger, recipient_email, data):
    url = settings.EMAIL_SERVICE_URL
    if not url:
        print("[Email Client WARNING]: EMAIL_SERVICE_URL is not configured in settings.")
        return
    
    payload = {
        "trigger": trigger,
        "recipient_email": recipient_email,
        "data": data
    }
    
    try:
        response = requests.post(url, json=payload, timeout=5)
        if response.status_code == 200:
            print(f"[Email Client SUCCESS]: Sent {trigger} notification to {recipient_email}")
        else:
            print(f"[Email Client ERROR]: Failed to send {trigger} to {recipient_email}. Status code: {response.status_code}. Response: {response.text}")
    except Exception as e:
        print(f"[Email Client ERROR]: Exception occurred sending {trigger} to {recipient_email}: {str(e)}")

def send_welcome_email(user):
    """
    Sends welcome email on signup trigger.
    """
    if not user.email:
        print(f"[Email Client] Skipping welcome email for {user.username} (no email address).")
        return
    
    data = {
        "username": user.username,
        "role": user.role
    }
    # Run in a background thread to prevent blocking the HTTP response thread
    thread = threading.Thread(target=_send_email_async, args=("SIGNUP_WELCOME", user.email, data))
    thread.daemon = True
    thread.start()

def send_booking_email(booking):
    """
    Sends booking confirmation emails to both Doctor and Patient.
    """
    start_str = booking.availability_slot.start_time.strftime('%Y-%m-%d %H:%M')
    end_str = booking.availability_slot.end_time.strftime('%H:%M')
    
    common_data = {
        "doctor_name": booking.doctor.full_name or booking.doctor.username,
        "patient_name": booking.patient.full_name or booking.patient.username,
        "start_time": f"{start_str} UTC",
        "end_time": f"{end_str} UTC"
    }

    # Send confirmation to patient
    if booking.patient.email:
        thread_patient = threading.Thread(target=_send_email_async, args=("BOOKING_CONFIRMATION", booking.patient.email, common_data))
        thread_patient.daemon = True
        thread_patient.start()
        
    # Send confirmation to doctor
    if booking.doctor.email:
        thread_doctor = threading.Thread(target=_send_email_async, args=("BOOKING_CONFIRMATION", booking.doctor.email, common_data))
        thread_doctor.daemon = True
        thread_doctor.start()
