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
        token = request.POST.get('device_token')
        toggle = request.POST.get('toggle')

        if token and toggle:
            try:
                device = GuardianDevice.objects.get(token=token)
                control, _ = GuardianControl.objects.get_or_create(device=device)

                new_state = (toggle == 'on')
                if control.enabled != new_state:
                    control.enabled = new_state
                    control.save()

                    GuardianLog.objects.create(
                        device=device,
                        log_text=f"🛰️ Guardian remote state set to {'ENABLED' if new_state else 'DISABLED'} via dashboard"
                    )

            except GuardianDevice.DoesNotExist:
                GuardianLog.objects.create(
                    device=None,
                    log_text=f"⚠️ Toggle failed — device not found: {token}"
                )

        return redirect('log_dashboard')  # ensure clean reload after POST

    return render(request, 'guardian/dashboard.html', {
        'logs': logs,
        'devices': devices,
    })

def device_control_json(request, token):
    device = get_object_or_404(GuardianDevice, token=token)
    try:
        control = device.control
        return JsonResponse({'status': 'on' if control.enabled else 'off'})
    except:
        return JsonResponse({'status': 'on'})  # Default fail-safe
