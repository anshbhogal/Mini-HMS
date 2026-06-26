import json
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

# Path to local logs
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
LOG_FILE = os.path.join(LOG_DIR, 'sent_emails.log')

def log_email_to_file(subject, recipient, body):
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR, exist_ok=True)
    
    log_entry = f"========================================\n"
    log_entry += f"Timestamp: {datetime.now().isoformat()}\n"
    log_entry += f"Recipient: {recipient}\n"
    log_entry += f"Subject: {subject}\n"
    log_entry += f"Body:\n{body}\n"
    log_entry += f"========================================\n\n"
    
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(log_entry)

def send_email(event, context):
    try:
        # Check event structure (serverless-offline wraps HTTP events)
        if 'body' in event:
            if isinstance(event['body'], str):
                body_data = json.loads(event['body'])
            else:
                body_data = event['body']
        else:
            body_data = event
        
        trigger = body_data.get('trigger')
        recipient_email = body_data.get('recipient_email')
        data = body_data.get('data', {})
        
        if not trigger or not recipient_email:
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "Missing trigger or recipient_email in payload."})
            }
        
        # Determine subject and body based on trigger
        if trigger == "SIGNUP_WELCOME":
            subject = "Welcome to Mini Hospital Management System"
            username = data.get('username', 'User')
            role = data.get('role', 'patient')
            body = (
                f"Hello {username},\n\n"
                f"Thank you for registering at Mini Hospital Management System as a {role.capitalize()}.\n"
                f"We are excited to have you on board!\n\n"
                f"Best regards,\n"
                f"Mini HMS Team"
            )
        elif trigger == "BOOKING_CONFIRMATION":
            subject = "Appointment Booking Confirmation - Mini HMS"
            doctor_name = data.get('doctor_name', 'Doctor')
            patient_name = data.get('patient_name', 'Patient')
            start_time = data.get('start_time', '')
            end_time = data.get('end_time', '')
            
            body = (
                f"Hello,\n\n"
                f"This email confirms your appointment booking:\n"
                f"- Doctor: Dr. {doctor_name}\n"
                f"- Patient: {patient_name}\n"
                f"- Scheduled Start: {start_time}\n"
                f"- Scheduled End: {end_time}\n\n"
                f"If you connected your Google Calendar, this event has also been added to your calendar.\n\n"
                f"Best regards,\n"
                f"Mini HMS Team"
            )
        else:
            return {
                "statusCode": 400,
                "body": json.dumps({"error": f"Invalid trigger '{trigger}'. Supported: SIGNUP_WELCOME, BOOKING_CONFIRMATION"})
            }
            
        # Send Email
        smtp_host = os.environ.get('EMAIL_SMTP_HOST', 'console')
        from_email = os.environ.get('EMAIL_FROM', 'no-reply@hms.com')
        
        # Always log to file for verification convenience
        log_email_to_file(subject, recipient_email, body)
        print(f"[Email Service] Trigger: {trigger} | Sent to: {recipient_email} | Subject: {subject}")
        
        if smtp_host.lower() == 'console' or not smtp_host:
            # Console mock mode
            return {
                "statusCode": 200,
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*"
                },
                "body": json.dumps({
                    "message": "Email logged to console and local file.",
                    "recipient": recipient_email,
                    "trigger": trigger,
                    "subject": subject
                })
            }
            
        # SMTP configuration
        smtp_port = int(os.environ.get('EMAIL_SMTP_PORT', '587'))
        smtp_user = os.environ.get('EMAIL_SMTP_USER', '')
        smtp_password = os.environ.get('EMAIL_SMTP_PASSWORD', '')
        
        msg = MIMEMultipart()
        msg['From'] = from_email
        msg['To'] = recipient_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))
        
        # Connect to SMTP server
        if smtp_port == 465:
            server = smtplib.SMTP_SSL(smtp_host, smtp_port)
        else:
            server = smtplib.SMTP(smtp_host, smtp_port)
            server.starttls()
            
        if smtp_user and smtp_password:
            server.login(smtp_user, smtp_password)
            
        server.sendmail(from_email, recipient_email, msg.as_string())
        server.quit()
        
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"
            },
            "body": json.dumps({
                "message": "Email sent successfully via SMTP.",
                "recipient": recipient_email,
                "trigger": trigger
            })
        }
        
    except Exception as e:
        print(f"[Email Service Error]: {str(e)}")
        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"
            },
            "body": json.dumps({"error": f"Internal Server Error: {str(e)}"})
        }
