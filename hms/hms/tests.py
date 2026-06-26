from django.test import TransactionTestCase, Client
from django.urls import reverse
from django.utils import timezone
from .models import User, Availability, Booking
import datetime
import threading
import time

class HMSTests(TransactionTestCase):

    def setUp(self):
        # Create test users
        self.doctor = User.objects.create_user(
            username='drsmith',
            email='drsmith@example.com',
            password='password123',
            role='doctor',
            full_name='Dr. Smith'
        )
        self.patient = User.objects.create_user(
            username='johndoe',
            email='johndoe@example.com',
            password='password123',
            role='patient',
            full_name='John Doe'
        )
        # Create availability slot in the future
        self.slot = Availability.objects.create(
            doctor=self.doctor,
            start_time=timezone.now() + datetime.timedelta(days=1),
            end_time=timezone.now() + datetime.timedelta(days=1, hours=1)
        )
        
    def test_role_based_access(self):
        """
        Verify that doctors cannot access patient actions and vice-versa.
        """
        client = Client()
        
        # 1. Unauthenticated redirects
        response = client.get(reverse('doctor_dashboard'))
        self.assertEqual(response.status_code, 302)
        response = client.get(reverse('patient_dashboard'))
        self.assertEqual(response.status_code, 302)
        
        # 2. Login as patient -> Forbidden for doctor dashboard
        client.login(username='johndoe', password='password123')
        response = client.get(reverse('doctor_dashboard'))
        self.assertEqual(response.status_code, 403)
        
        # Patient dashboard -> Success
        response = client.get(reverse('patient_dashboard'))
        self.assertEqual(response.status_code, 200)
        client.logout()
        
        # 3. Login as doctor -> Forbidden for patient dashboard
        client.login(username='drsmith', password='password123')
        response = client.get(reverse('patient_dashboard'))
        self.assertEqual(response.status_code, 403)
        
        # Doctor dashboard -> Success
        response = client.get(reverse('doctor_dashboard'))
        self.assertEqual(response.status_code, 200)
        client.logout()
        
    def test_booking_success(self):
        """
        Tests successful appointment booking flow.
        """
        client = Client()
        client.login(username='johndoe', password='password123')
        
        response = client.post(reverse('book_slot', args=[self.slot.id]))
        self.assertEqual(response.status_code, 302) # Redirects back to dashboard
        
        # Refresh and inspect slot
        self.slot.refresh_from_db()
        self.assertTrue(self.slot.is_booked)
        
        # Inspect booking
        booking = Booking.objects.get(availability_slot=self.slot)
        self.assertEqual(booking.patient, self.patient)
        self.assertEqual(booking.doctor, self.doctor)
        
    def test_cannot_book_already_booked_slot(self):
        """
        Verify a slot cannot be booked again.
        """
        self.slot.is_booked = True
        self.slot.save()
        
        client = Client()
        client.login(username='johndoe', password='password123')
        
        response = client.post(reverse('book_slot', args=[self.slot.id]))
        # Should redirect with warning messages and not create any booking records
        self.assertEqual(Booking.objects.filter(availability_slot=self.slot).count(), 0)

    def test_booking_race_condition(self):
        """
        Simulate concurrent booking attempts for the same availability slot.
        Verifies database locking prevents duplicate/double bookings.
        """
        # Create second patient
        patient2 = User.objects.create_user(
            username='maryjane',
            email='mary@example.com',
            password='password123',
            role='patient',
            full_name='Mary Jane'
        )
        
        # Instantiate and log in clients BEFORE starting threads to avoid SQLite session write conflicts
        c1 = Client()
        c1.login(username='johndoe', password='password123')
        
        c2 = Client()
        c2.login(username='maryjane', password='password123')
        
        results = []
        errors = []
        
        def attempt_booking(client):
            try:
                response = client.post(reverse('book_slot', args=[self.slot.id]))
                results.append(response)
            except Exception as e:
                errors.append(str(e))

        # Launch two parallel booking threads
        t1 = threading.Thread(target=attempt_booking, args=(c1,))
        t2 = threading.Thread(target=attempt_booking, args=(c2,))
        
        t1.start()
        t2.start()
        
        t1.join()
        t2.join()
        
        # Check booking count: Exactly 1 booking should be successfully created
        booking_count = Booking.objects.filter(availability_slot=self.slot).count()
        if booking_count != 1:
            print(f"RACE CONDITION TEST DETAILS: errors={errors}, results={[r.status_code for r in results]}")
        self.assertEqual(booking_count, 1)
        
        self.slot.refresh_from_db()
        self.assertTrue(self.slot.is_booked)


