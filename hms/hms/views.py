import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.http import HttpResponseForbidden

from .models import User, Availability, Booking, GoogleCredentials
from .emails import send_welcome_email, send_booking_email
from .calendar_sync import create_calendar_events

from google_auth_oauthlib.flow import Flow
from django.conf import settings

# Decorators for role checks
def doctor_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated or request.user.role != 'doctor':
            return HttpResponseForbidden("Access Denied: Only Doctors can perform this action.")
        return view_func(request, *args, **kwargs)
    return wrapper

def patient_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated or request.user.role != 'patient':
            return HttpResponseForbidden("Access Denied: Only Patients can perform this action.")
        return view_func(request, *args, **kwargs)
    return wrapper


def index(request):
    """
    Landing page for Mini HMS.
    """
    if request.user.is_authenticated:
        return redirect('doctor_dashboard' if request.user.role == 'doctor' else 'patient_dashboard')
    return render(request, 'index.html')


def signup_view(request):
    """
    Handles Doctor and Patient registrations.
    Triggers SIGNUP_WELCOME notification.
    """
    if request.user.is_authenticated:
        return redirect('doctor_dashboard' if request.user.role == 'doctor' else 'patient_dashboard')
        
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        role = request.POST.get('role')
        full_name = request.POST.get('full_name', '')
        
        if not username or not email or not password or not role:
            messages.error(request, "All fields are required.")
            return render(request, 'signup.html')
            
        if role not in ['doctor', 'patient']:
            messages.error(request, "Invalid role selected.")
            return render(request, 'signup.html')
            
        if User.objects.filter(username=username).exists():
            messages.error(request, "Username is already taken.")
            return render(request, 'signup.html')
            
        if User.objects.filter(email=email).exists():
            messages.error(request, "Email address is already registered.")
            return render(request, 'signup.html')
            
        # Create user
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            role=role,
            full_name=full_name
        )
        
        # Trigger welcome email asynchronously
        send_welcome_email(user)
        
        login(request, user)
        messages.success(request, f"Welcome to Mini HMS, {user.get_display_name()}!")
        return redirect('doctor_dashboard' if role == 'doctor' else 'patient_dashboard')
        
    return render(request, 'signup.html')


def login_view(request):
    """
    Handles logging in of Doctor/Patient.
    """
    if request.user.is_authenticated:
        return redirect('doctor_dashboard' if request.user.role == 'doctor' else 'patient_dashboard')
        
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            messages.success(request, f"Welcome back, {user.get_display_name()}!")
            return redirect('doctor_dashboard' if user.role == 'doctor' else 'patient_dashboard')
        else:
            messages.error(request, "Invalid credentials. Please try again.")
            
    return render(request, 'login.html')


def logout_view(request):
    """
    Logs out the user.
    """
    logout(request)
    messages.success(request, "You have logged out successfully.")
    return redirect('index')


@login_required
@doctor_required
def doctor_dashboard(request):
    """
    Dashboard for doctors to setup availability slots and check bookings.
    """
    # Show doctor's availability
    availabilities = Availability.objects.filter(doctor=request.user).order_by('start_time')
    
    if request.method == 'POST':
        start_time_str = request.POST.get('start_time')
        end_time_str = request.POST.get('end_time')
        
        if start_time_str and end_time_str:
            try:
                # Parse date local time
                start_time = timezone.make_aware(datetime.datetime.strptime(start_time_str, '%Y-%m-%dT%H:%M'))
                end_time = timezone.make_aware(datetime.datetime.strptime(end_time_str, '%Y-%m-%dT%H:%M'))
                
                # Check overlapping slots
                overlap_exists = Availability.objects.filter(
                    doctor=request.user,
                    start_time__lt=end_time,
                    end_time__gt=start_time
                ).exists()
                
                if overlap_exists:
                    messages.error(request, "A slot already overlaps with this timeframe.")
                else:
                    slot = Availability(
                        doctor=request.user,
                        start_time=start_time,
                        end_time=end_time
                    )
                    slot.save()
                    messages.success(request, "Availability slot created successfully.")
                    return redirect('doctor_dashboard')
            except ValueError:
                messages.error(request, "Invalid time format.")
            except ValidationError as e:
                messages.error(request, str(e))
        else:
            messages.error(request, "Both start and end time parameters are required.")
            
    has_calendar = GoogleCredentials.objects.filter(user=request.user).exists()
    
    context = {
        'availabilities': availabilities,
        'has_calendar': has_calendar
    }
    return render(request, 'doctor_dashboard.html', context)


@login_required
@patient_required
def patient_dashboard(request):
    """
    Dashboard for patients to search doctors, view slots, and manage bookings.
    """
    doctors = User.objects.filter(role='doctor')
    selected_doctor_id = request.GET.get('doctor_id')
    
    availabilities = []
    selected_doctor = None
    if selected_doctor_id:
        selected_doctor = get_object_or_404(User, id=selected_doctor_id, role='doctor')
        # Display future available slots only
        availabilities = Availability.objects.filter(
            doctor=selected_doctor,
            start_time__gt=timezone.now(),
            is_booked=False
        ).order_by('start_time')
        
    my_bookings = Booking.objects.filter(patient=request.user).order_by('-availability_slot__start_time')
    has_calendar = GoogleCredentials.objects.filter(user=request.user).exists()
    
    context = {
        'doctors': doctors,
        'selected_doctor': selected_doctor,
        'availabilities': availabilities,
        'my_bookings': my_bookings,
        'has_calendar': has_calendar
    }
    return render(request, 'patient_dashboard.html', context)


@login_required
@patient_required
def book_slot(request, slot_id):
    """
    Secure booking action. Locks the slot record using database transactions
    to handle potential booking race conditions.
    """
    if request.method != 'POST':
        return redirect('patient_dashboard')
        
    try:
        # Wrap in a database atomic transaction
        with transaction.atomic():
            # select_for_update locks the slot row in the DB until the transaction commits
            slot = Availability.objects.select_for_update().get(id=slot_id)
            
            if slot.is_booked:
                messages.error(request, "Sorry, this slot has already been booked by another patient.")
                return redirect('patient_dashboard')
                
            if slot.start_time <= timezone.now():
                messages.error(request, "This slot has expired (is in the past).")
                return redirect('patient_dashboard')
                
            # Perform Booking
            slot.is_booked = True
            slot.save()
            
            booking = Booking.objects.create(
                patient=request.user,
                doctor=slot.doctor,
                availability_slot=slot
            )
            
        # Database transaction is completed and unlocked here.
        # Now trigger external integrations asynchronously to avoid holding DB lock.
        
        # 1. Sync Calendar
        create_calendar_events(booking)
        
        # 2. Email Notification
        send_booking_email(booking)
        
        messages.success(request, f"Successfully booked appointment with {booking.doctor.get_display_name()}!")
    except Availability.DoesNotExist:
        messages.error(request, "The selected slot does not exist.")
    except Exception as e:
        messages.error(request, f"Error booking appointment: {str(e)}")
        
    return redirect('patient_dashboard')


@login_required
def google_connect(request):
    """
    Redirects the user to Google OAuth2 consent screen.
    If no client secrets are configured, redirects to mock connect to facilitate local testing.
    """
    client_id = settings.GOOGLE_CLIENT_ID
    client_secret = settings.GOOGLE_CLIENT_SECRET
    
    # Local developer mock fallback
    if not client_id or not client_secret:
        # Create a mock credential in the database directly
        GoogleCredentials.from_dict(request.user, {
            'token': 'mock-access-token-123',
            'refresh_token': 'mock-refresh-token-123',
            'token_uri': 'https://oauth2.googleapis.com/token',
            'client_id': 'mock-client-id',
            'client_secret': 'mock-client-secret',
            'scopes': ['https://www.googleapis.com/auth/calendar.events']
        })
        messages.success(request, "Google Calendar connected in Mock Mode (Console logs used).")
        return redirect('doctor_dashboard' if request.user.role == 'doctor' else 'patient_dashboard')
        
    # Standard Google OAuth flow
    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=['https://www.googleapis.com/auth/calendar.events'],
        redirect_uri=settings.GOOGLE_REDIRECT_URI
    )
    
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true'
    )
    
    request.session['google_oauth_state'] = state
    return redirect(authorization_url)


@login_required
def google_oauth_callback(request):
    """
    Google OAuth2 Callback url. Receives auth token and creates credentials link.
    """
    client_id = settings.GOOGLE_CLIENT_ID
    client_secret = settings.GOOGLE_CLIENT_SECRET
    
    if not client_id or not client_secret:
        messages.error(request, "Google OAuth configurations are missing.")
        return redirect('doctor_dashboard' if request.user.role == 'doctor' else 'patient_dashboard')
        
    state = request.session.get('google_oauth_state')
    
    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=['https://www.googleapis.com/auth/calendar.events'],
        state=state,
        redirect_uri=settings.GOOGLE_REDIRECT_URI
    )
    
    flow.fetch_token(authorization_response=request.build_absolute_uri())
    credentials = flow.credentials
    
    GoogleCredentials.from_dict(request.user, {
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
        'scopes': credentials.scopes
    })
    
    messages.success(request, "Your Google Calendar is successfully linked!")
    return redirect('doctor_dashboard' if request.user.role == 'doctor' else 'patient_dashboard')
