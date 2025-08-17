import os
import stripe
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from .forms import RegistrationForm, AudioFileForm
from django.contrib.auth.decorators import login_required
from .models import AudioFile, ProcessedAudioFile, ShowNotes, SubscriptionPlan, UserSubscription
from deepgram import DeepgramClient, PrerecordedOptions
from pydub import AudioSegment
from django.conf import settings
from django.core.files.base import ContentFile
import openai
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt

# TODO: Replace with your API Keys
DEEPGRAM_API_KEY = os.environ.get("DEEPGRAM_API_KEY")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
STRIPE_API_KEY = os.environ.get("STRIPE_API_KEY")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET")

stripe.api_key = STRIPE_API_KEY

def index(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, "index.html")

@login_required
def dashboard(request):
    audio_files = AudioFile.objects.filter(user=request.user)
    processed_audio_files = ProcessedAudioFile.objects.filter(original_file__user=request.user)
    show_notes = ShowNotes.objects.filter(audio_file__user=request.user)

    try:
        subscription = UserSubscription.objects.get(user=request.user)
    except UserSubscription.DoesNotExist:
        subscription = None

    return render(request, "dashboard.html", {
        "audio_files": audio_files,
        "processed_audio_files": processed_audio_files,
        "show_notes": show_notes,
        "subscription": subscription,
    })

@login_required
def upload_file(request):
    if request.method == 'POST':
        form = AudioFileForm(request.POST, request.FILES)
        if form.is_valid():
            audio_file = form.save(commit=False)
            audio_file.user = request.user
            audio_file.save()
            return redirect('index')
    else:
        form = AudioFileForm()
    return render(request, 'upload_file.html', {'form': form})

from django.contrib.auth.models import User

def register(request):
    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = User.objects.create_user(
                username=form.cleaned_data['username'],
                email=form.cleaned_data['email'],
                password=form.cleaned_data['password']
            )
            # Create a user subscription object
            UserSubscription.objects.create(user=user)
            return redirect('index')
    else:
        form = RegistrationForm()
    return render(request, 'registration/register.html', {'form': form})

from django.contrib import messages

@login_required
def de_um_audio(request, audio_file_id):
    audio_file = get_object_or_404(AudioFile, id=audio_file_id, user=request.user)
    subscription = get_object_or_404(UserSubscription, user=request.user)

    # Check if the user has enough processing time
    audio = AudioSegment.from_file(audio_file.audio_file.path)
    duration_hours = len(audio) / (1000 * 60 * 60)

    if subscription.remaining_processing_hours < duration_hours:
        messages.error(request, "You don't have enough processing time left in your subscription.")
        return redirect('dashboard')

    processed_file_path, processed_filename = process_audio_with_deepgram(audio_file.audio_file.path)

    if processed_file_path:
        with open(processed_file_path, 'rb') as f:
            processed_audio_file = ProcessedAudioFile(original_file=audio_file)
            processed_audio_file.processed_file.save(processed_filename, ContentFile(f.read()))
            processed_audio_file.save()

            # Deduct the processing time
            subscription.remaining_processing_hours -= duration_hours
            subscription.save()
            messages.success(request, "Your audio has been processed successfully.")

    return redirect('dashboard')

def process_audio_with_deepgram(audio_file_path):
    if not DEEPGRAM_API_KEY:
        raise Exception("Deepgram API key not found.")

    deepgram = DeepgramClient(DEEPGRAM_API_KEY)

    with open(audio_file_path, "rb") as file:
        buffer_data = file.read()

    payload = {
        "buffer": buffer_data,
    }

    options = PrerecordedOptions(
        model="nova-2",
        smart_format=True,
        utterances=True,
        punctuate=True,
        filler_words=True,
    )

    response = deepgram.listen.prerecorded.v("1").transcribe_file(
        payload, options
    )

    words = response.results.channels[0].alternatives[0].words
    filler_timestamps = []
    for word in words:
        if hasattr(word, 'filler') and word.filler:
             filler_timestamps.append((word.start, word.end))

    if not filler_timestamps:
        return None, None

    original_audio = AudioSegment.from_file(audio_file_path)
    processed_audio = AudioSegment.empty()

    last_end_time = 0
    for start_time, end_time in filler_timestamps:
        start_ms = int(start_time * 1000)
        end_ms = int(end_time * 1000)

        processed_audio += original_audio[last_end_time:start_ms]
        last_end_time = end_ms

    processed_audio += original_audio[last_end_time:]

    processed_filename = f"processed_{os.path.basename(audio_file_path)}"
    processed_file_path = os.path.join(settings.MEDIA_ROOT, processed_filename)
    processed_audio.export(processed_file_path, format="mp3")

    return processed_file_path, processed_filename

@login_required
def generate_show_notes(request, audio_file_id):
    audio_file = get_object_or_404(AudioFile, id=audio_file_id, user=request.user)
    subscription = get_object_or_404(UserSubscription, user=request.user)

    # Check if the user has enough processing time
    audio = AudioSegment.from_file(audio_file.audio_file.path)
    duration_hours = len(audio) / (1000 * 60 * 60)

    if subscription.remaining_processing_hours < duration_hours:
        messages.error(request, "You don't have enough processing time left in your subscription.")
        return redirect('dashboard')

    transcript = get_transcript(audio_file.audio_file.path)

    if transcript:
        notes = process_with_llm(transcript)
        ShowNotes.objects.create(audio_file=audio_file, notes=notes)

        # Deduct the processing time
        subscription.remaining_processing_hours -= duration_hours
        subscription.save()
        messages.success(request, "Your show notes have been generated successfully.")

    return redirect('dashboard')

def get_transcript(audio_file_path):
    if not DEEPGRAM_API_KEY:
        raise Exception("Deepgram API key not found.")

    deepgram = DeepgramClient(DEEPGRAM_API_KEY)

    with open(audio_file_path, "rb") as file:
        buffer_data = file.read()

    payload = {
        "buffer": buffer_data,
    }

    options = PrerecordedOptions(
        model="nova-2",
        smart_format=True,
    )

    response = deepgram.listen.prerecorded.v("1").transcribe_file(
        payload, options
    )

    return response.results.channels[0].alternatives[0].transcript

def process_with_llm(transcript):
    if not OPENAI_API_KEY:
        raise Exception("OpenAI API key not found.")

    openai.api_key = OPENAI_API_KEY

    prompt = f"""
    You are a helpful assistant for a podcaster. You have been given the transcript of a podcast episode.
    Your task is to generate a set of show notes for this episode.
    The show notes should be in the following format:

    **Summary:**
    A 3-4 sentence summary of the episode.

    **Main Topics:**
    A bulleted list of the main topics discussed, with the corresponding start timestamp for each topic.
    (You will need to infer the timestamps based on the flow of the conversation in the transcript. This is a creative task.)

    **Mentioned Resources:**
    A list of any books, websites, or products mentioned in the episode.

    Here is the transcript:
    ---
    {transcript}
    ---
    """

    response = openai.Completion.create(
        engine="text-davinci-003",
        prompt=prompt,
        max_tokens=500
    )

    return response.choices[0].text.strip()

@login_required
def pricing(request):
    plans = SubscriptionPlan.objects.all()
    return render(request, 'pricing.html', {'plans': plans})

@login_required
def create_checkout_session(request, price_id):
    subscription = get_object_or_404(UserSubscription, user=request.user)

    if not subscription.stripe_customer_id:
        customer = stripe.Customer.create(
            email=request.user.email,
            name=request.user.username,
        )
        subscription.stripe_customer_id = customer.id
        subscription.save()

    try:
        checkout_session = stripe.checkout.Session.create(
            customer=subscription.stripe_customer_id,
            client_reference_id=request.user.id,
            success_url=request.build_absolute_uri('/success?session_id={CHECKOUT_SESSION_ID}'),
            cancel_url=request.build_absolute_uri('/cancel'),
            payment_method_types=['card'],
            mode='subscription',
            line_items=[{
                'price': price_id,
                'quantity': 1,
            }]
        )
        return redirect(checkout_session.url)
    except Exception as e:
        return render(request, 'error.html', {'error': str(e)})

@login_required
def success(request):
    return render(request, 'success.html')

@login_required
def cancel(request):
    return render(request, 'cancel.html')

@login_required
def create_portal_session(request):
    subscription = get_object_or_404(UserSubscription, user=request.user)
    portal_session = stripe.billing_portal.Session.create(
        customer=subscription.stripe_customer_id,
        return_url=request.build_absolute_uri(reverse('dashboard')),
    )
    return redirect(portal_session.url)

import noisereduce as nr
from scipy.io import wavfile

@csrf_exempt
def stripe_webhook(request):
    payload = request.body
    sig_header = request.META['HTTP_STRIPE_SIGNATURE']
    event = None

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        # Invalid payload
        return HttpResponse(status=400)
    except stripe.error.SignatureVerificationError as e:
        # Invalid signature
        return HttpResponse(status=400)

    # Handle the event
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        user_id = session['client_reference_id']
        stripe_subscription_id = session['subscription']

        user = User.objects.get(id=user_id)
        subscription = UserSubscription.objects.get(user=user)
        subscription.stripe_subscription_id = stripe_subscription_id
        subscription.is_active = True

        # Get the plan from the session
        price_id = session['line_items']['data'][0]['price']['id']
        plan = SubscriptionPlan.objects.get(stripe_price_id=price_id)
        subscription.subscription_plan = plan
        subscription.remaining_processing_hours = plan.processing_hours

        subscription.save()

    elif event['type'] == 'customer.subscription.updated':
        session = event['data']['object']
        stripe_subscription_id = session['id']
        subscription = UserSubscription.objects.get(stripe_subscription_id=stripe_subscription_id)

        # Get the new plan
        price_id = session['items']['data'][0]['price']['id']
        plan = SubscriptionPlan.objects.get(stripe_price_id=price_id)
        subscription.subscription_plan = plan
        subscription.remaining_processing_hours = plan.processing_hours

        subscription.save()

    elif event['type'] == 'customer.subscription.deleted':
        session = event['data']['object']
        stripe_subscription_id = session['id']
        subscription = UserSubscription.objects.get(stripe_subscription_id=stripe_subscription_id)
        subscription.is_active = False
        subscription.save()

    return HttpResponse(status=200)

@login_required
def reduce_noise_view(request, audio_file_id):
    audio_file = get_object_or_404(AudioFile, id=audio_file_id, user=request.user)
    subscription = get_object_or_404(UserSubscription, user=request.user)

    # Check if the user has enough processing time
    audio = AudioSegment.from_file(audio_file.audio_file.path)
    duration_hours = len(audio) / (1000 * 60 * 60)

    if subscription.remaining_processing_hours < duration_hours:
        messages.error(request, "You don't have enough processing time left in your subscription.")
        return redirect('dashboard')

    processed_file_path, processed_filename = reduce_noise(audio_file.audio_file.path)

    if processed_file_path:
        with open(processed_file_path, 'rb') as f:
            processed_audio_file = ProcessedAudioFile(original_file=audio_file)
            processed_audio_file.processed_file.save(processed_filename, ContentFile(f.read()))
            processed_audio_file.save()

            # Deduct the processing time
            subscription.remaining_processing_hours -= duration_hours
            subscription.save()
            messages.success(request, "Noise reduction has been applied successfully.")

    return redirect('dashboard')


def reduce_noise(audio_file_path):
    # Convert to wav
    audio = AudioSegment.from_file(audio_file_path)
    wav_path = audio_file_path + ".wav"
    audio.export(wav_path, format="wav")

    rate, data = wavfile.read(wav_path)
    # perform noise reduction
    reduced_noise = nr.reduce_noise(y=data, sr=rate, prop_decrease=0.8)

    processed_filename = f"processed_nr_{os.path.basename(audio_file_path)}"
    processed_file_path = os.path.join(settings.MEDIA_ROOT, processed_filename)

    wavfile.write(processed_file_path, rate, reduced_noise)

    # Clean up the temporary wav file
    os.remove(wav_path)

    return processed_file_path, processed_filename
