from .models import GuardianControl, GuardianLog, GuardianDevice

from django.shortcuts import get_object_or_404, render, redirect
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.timezone import now
from rest_framework.decorators import api_view
from rest_framework.response import Response
from .serializers import GuardianLogSerializer

def control_json(request):
    try:
        control = GuardianControl.objects.first()
        if not control:
            control = GuardianControl.objects.create(enabled=True)
        return JsonResponse({'status': 'on' if control.enabled else 'off'})
    except Exception as e:
        return JsonResponse({'status': 'on'})  # fail-safe default

@csrf_exempt
def upload_log(request):
    if request.method != 'POST':
        return HttpResponse("Method Not Allowed", status=405)

    token = request.headers.get('X-DEVICE-TOKEN')
    log_text = request.body.decode('utf-8')

    if not token or not log_text:
        return JsonResponse({'error': 'Missing token or log_text'}, status=400)

    device, _ = GuardianDevice.objects.get_or_create(token=token)
    device.last_seen = now()
    device.save()

    GuardianLog.objects.create(device=device, log_text=log_text)

    return HttpResponse("OK", status=200)

@api_view(['GET'])
def get_device_logs(request):
    token = request.headers.get('X-DEVICE-TOKEN')
    if not token:
        return Response({'error': 'Missing token'}, status=400)

    try:
        device = GuardianDevice.objects.get(token=token)
    except GuardianDevice.DoesNotExist:
        return Response({'error': 'Device not registered'}, status=404)

    logs = device.logs.order_by('-timestamp')[:50]  # latest 50 logs
    serializer = GuardianLogSerializer(logs, many=True)
    return Response(serializer.data)

def log_dashboard(request):
    logs = GuardianLog.objects.select_related('device').order_by('-timestamp')[:200]
    devices = GuardianDevice.objects.all()

    if request.method == 'POST':
        submitted_token = request.POST.get("submit_token")

        if submitted_token:
            try:
                device = GuardianDevice.objects.get(token=submitted_token)

                # Extract POST states
                override_enabled = f"override_{device.token}" in request.POST
                forced_state = request.POST.get(f"force_{device.token}") == "on"
                simulate_lock = f"simulate_{device.token}" in request.POST  # ✅ New flag

                # Save changes to device
                device.override_enabled = override_enabled
                device.override_value = forced_state
                device.simulate_watu_lock = simulate_lock  # ✅ Save simulation intent
                device.save()

                # Logging actions
                GuardianLog.objects.create(
                    device=device,
                    log_text=f"🛰️ Remote override {'ENABLED' if override_enabled else 'DISABLED'} — State: {'ON' if forced_state else 'OFF'}"
                )

                if simulate_lock:
                    GuardianLog.objects.create(
                        device=device,
                        log_text=f"🧪 Simulated Watu lock manually triggered from dashboard"
                    )

            except GuardianDevice.DoesNotExist:
                GuardianLog.objects.create(
                    device=None,
                    log_text=f"⚠️ Override failed — device not found: {submitted_token}"
                )

        return redirect('guardian-log-dashboard')

    return render(request, 'guardian/dashboard.html', {
        'logs': logs,
        'devices': devices,
    })

def device_control_json(request, token):
    device = get_object_or_404(GuardianDevice, token=token)

    simulate_flag = device.simulate_watu_lock  # capture current state before clearing

    # Auto-reset after reading
    if simulate_flag:
        device.simulate_watu_lock = False
        device.save()
        GuardianLog.objects.create(
            device=device,
            log_text="🧪 simulate_watu_lock was triggered and has now been reset"
        )

    # Handle override
    if device.override_enabled:
        GuardianLog.objects.create(
            device=device,
            log_text=f"🛰️ Remote override ENABLED — State: {'ON' if device.override_value else 'OFF'}"
        )
        return JsonResponse({
            'status': 'override',
            'value': 'on' if device.override_value else 'off',
            'simulate_watu': simulate_flag
        })

    # Default device control fallback
    control = GuardianControl.objects.filter(device=device).first()
    GuardianLog.objects.create(
        device=device,
        log_text=f"📶 Remote check: Guardian is {'ENABLED' if control and control.enabled else 'DISABLED'}"
    )

    return JsonResponse({
        'status': 'on' if (control and control.enabled) else 'off',
        'simulate_watu': simulate_flag
    })
