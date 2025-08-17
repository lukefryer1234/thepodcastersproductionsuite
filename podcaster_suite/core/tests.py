from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from .models import AudioFile, ProcessedAudioFile, ShowNotes, SubscriptionPlan, UserSubscription
from django.core.files.uploadedfile import SimpleUploadedFile
from django.conf import settings
import os
import shutil
from unittest.mock import patch

class CoreViewsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='testuser', password='testpassword')
        self.client.login(username='testuser', password='testpassword')

    def test_index_view_authenticated(self):
        response = self.client.get(reverse('index'))
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('dashboard'))

    def test_index_view_unauthenticated(self):
        self.client.logout()
        response = self.client.get(reverse('index'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'index.html')

    def test_upload_file_view_get(self):
        response = self.client.get(reverse('upload_file'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'upload_file.html')

    def test_upload_file_view_post(self):
        # Create a dummy audio file
        audio_content = b'This is a test audio file.'
        audio_file = SimpleUploadedFile("test_audio.mp3", audio_content, content_type="audio/mpeg")

        response = self.client.post(reverse('upload_file'), {
            'title': 'Test Audio',
            'audio_file': audio_file,
        })

        self.assertEqual(response.status_code, 302) # Should redirect to index
        self.assertEqual(AudioFile.objects.count(), 1)
        self.assertEqual(AudioFile.objects.first().title, 'Test Audio')

    def test_upload_file_view_post_m4a(self):
        # Create a dummy audio file
        audio_content = b'This is a test audio file.'
        audio_file = SimpleUploadedFile("test_audio.m4a", audio_content, content_type="audio/mp4")

        response = self.client.post(reverse('upload_file'), {
            'title': 'Test Audio M4A',
            'audio_file': audio_file,
        })

        self.assertEqual(response.status_code, 302) # Should redirect to index
        self.assertEqual(AudioFile.objects.count(), 1)
        self.assertEqual(AudioFile.objects.first().title, 'Test Audio M4A')

class AuthViewsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user_credentials = {
            'username': 'testuser',
            'password': 'testpassword',
            'email': 'test@example.com',
        }
        self.user = User.objects.create_user(**self.user_credentials)

    def test_login_view(self):
        response = self.client.post(reverse('login'), {
            'username': self.user_credentials['username'],
            'password': self.user_credentials['password'],
        })
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('dashboard'))

    def test_logout_view(self):
        self.client.login(username=self.user_credentials['username'], password=self.user_credentials['password'])
        response = self.client.post(reverse('logout'))
        self.assertEqual(response.status_code, 302) # Should redirect to index
        self.assertRedirects(response, reverse('index'))

    def test_register_view(self):
        response = self.client.post(reverse('register'), {
            'username': 'newuser',
            'password': 'newpassword123',
            'password2': 'newpassword123',
            'email': 'new@example.com'
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(User.objects.count(), 2)

class ModelsTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpassword')
        self.plan = SubscriptionPlan.objects.create(name='Test Plan', stripe_price_id='price_123', price=10.00, processing_hours=5)

    def test_audio_file_model(self):
        audio_file = AudioFile.objects.create(user=self.user, title='Test Audio', audio_file='test.mp3')
        self.assertEqual(str(audio_file), 'Test Audio')

    def test_processed_audio_file_model(self):
        audio_file = AudioFile.objects.create(user=self.user, title='Test Audio', audio_file='test.mp3')
        processed_audio = ProcessedAudioFile.objects.create(original_file=audio_file, processed_file='processed.mp3')
        self.assertEqual(str(processed_audio), 'Processed version of Test Audio')

    def test_show_notes_model(self):
        audio_file = AudioFile.objects.create(user=self.user, title='Test Audio', audio_file='test.mp3')
        show_notes = ShowNotes.objects.create(audio_file=audio_file, notes='These are the show notes.')
        self.assertEqual(str(show_notes), 'Show notes for Test Audio')

    def test_subscription_plan_model(self):
        self.assertEqual(str(self.plan), 'Test Plan')

    def test_user_subscription_model(self):
        user_sub = UserSubscription.objects.create(user=self.user, subscription_plan=self.plan)
        self.assertEqual(str(user_sub), "testuser's subscription")

class DashboardViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='testuser', password='testpassword')
        self.plan = SubscriptionPlan.objects.create(name='Test Plan', stripe_price_id='price_123', price=10.00, processing_hours=5)
        self.subscription = UserSubscription.objects.create(user=self.user, subscription_plan=self.plan, is_active=True, remaining_processing_hours=5)

    def test_dashboard_view_authenticated(self):
        self.client.login(username='testuser', password='testpassword')
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'dashboard.html')
        self.assertContains(response, 'Test Plan')
        self.assertContains(response, 'Active')
        self.assertContains(response, '5 hours')

    def test_dashboard_view_unauthenticated(self):
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, f"{reverse('login')}?next={reverse('dashboard')}")

class SubscriptionManagementTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='testuser', password='testpassword')
        self.plan = SubscriptionPlan.objects.create(name='Test Plan', stripe_price_id='price_123', price=10.00, processing_hours=5)
        self.subscription = UserSubscription.objects.create(user=self.user, subscription_plan=self.plan, is_active=True, stripe_customer_id='cus_123')

    def test_manage_subscription_button_present(self):
        self.client.login(username='testuser', password='testpassword')
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, 'Manage Subscription')

    @patch('stripe.billing_portal.Session.create')
    def test_create_portal_session_redirects(self, mock_create_session):
        mock_create_session.return_value = type('obj', (object,), {'url': 'https://stripe.com/portal'})
        self.client.login(username='testuser', password='testpassword')
        response = self.client.get(reverse('create_portal_session'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, 'https://stripe.com/portal')

class ProcessingTimeTest(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        os.makedirs(settings.MEDIA_ROOT, exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(settings.MEDIA_ROOT)
        super().tearDownClass()

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='testuser', password='testpassword')
        self.plan = SubscriptionPlan.objects.create(name='Test Plan', stripe_price_id='price_123', price=10.00, processing_hours=5)
        self.subscription = UserSubscription.objects.create(user=self.user, subscription_plan=self.plan, is_active=True, remaining_processing_hours=5)

        self.audio_content = b'This is a test audio file.'
        self.audio_file_obj = SimpleUploadedFile("test.mp3", self.audio_content, content_type="audio/mpeg")
        self.audio_file = AudioFile.objects.create(user=self.user, title='Test Audio', audio_file=self.audio_file_obj)

    @patch('core.views.process_audio_with_deepgram')
    @patch('pydub.AudioSegment.from_file')
    def test_deduct_processing_time_de_um(self, mock_from_file, mock_process_audio):
        mock_audio = type('obj', (object,), {'__len__': lambda self: 3600 * 1000})() # 1 hour
        mock_from_file.return_value = mock_audio

        processed_filename = 'processed.mp3'
        processed_file_path = os.path.join(settings.MEDIA_ROOT, processed_filename)
        with open(processed_file_path, 'wb') as f:
            f.write(self.audio_content)

        mock_process_audio.return_value = (processed_file_path, processed_filename)

        self.client.login(username='testuser', password='testpassword')
        self.client.get(reverse('de_um_audio', args=[self.audio_file.id]))

        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.remaining_processing_hours, 4)

    @patch('core.views.get_transcript')
    @patch('core.views.process_with_llm')
    @patch('pydub.AudioSegment.from_file')
    def test_deduct_processing_time_show_notes(self, mock_from_file, mock_process_llm, mock_get_transcript):
        mock_audio = type('obj', (object,), {'__len__': lambda self: 3600 * 1000})() # 1 hour
        mock_from_file.return_value = mock_audio
        mock_get_transcript.return_value = "This is a transcript."
        mock_process_llm.return_value = "These are the show notes."

        self.client.login(username='testuser', password='testpassword')
        self.client.get(reverse('generate_show_notes', args=[self.audio_file.id]))

        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.remaining_processing_hours, 4)

    @patch('pydub.AudioSegment.from_file')
    def test_insufficient_processing_time(self, mock_from_file):
        mock_audio = type('obj', (object,), {'__len__': lambda self: 3600 * 1000 * 6})() # 6 hours
        mock_from_file.return_value = mock_audio

        self.client.login(username='testuser', password='testpassword')
        response = self.client.get(reverse('de_um_audio', args=[self.audio_file.id]))

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('dashboard'))
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.remaining_processing_hours, 5)

    @patch('core.views.reduce_noise')
    @patch('pydub.AudioSegment.from_file')
    def test_reduce_noise_view(self, mock_from_file, mock_reduce_noise):
        mock_audio = type('obj', (object,), {'__len__': lambda self: 3600 * 1000})() # 1 hour
        mock_from_file.return_value = mock_audio

        processed_filename = 'processed_nr.mp3'
        processed_file_path = os.path.join(settings.MEDIA_ROOT, processed_filename)
        with open(processed_file_path, 'wb') as f:
            f.write(self.audio_content)

        mock_reduce_noise.return_value = (processed_file_path, processed_filename)

        self.client.login(username='testuser', password='testpassword')
        self.client.get(reverse('reduce_noise_view', args=[self.audio_file.id]))

        self.assertEqual(ProcessedAudioFile.objects.count(), 1)
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.remaining_processing_hours, 4)
