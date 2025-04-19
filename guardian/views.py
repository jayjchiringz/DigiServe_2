from .models import GuardianApkUpdate, GuardianControl, GuardianLog, GuardianDevice, GuardianPatch

from django.shortcuts import get_object_or_404, render, redirect
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.timezone import now
from django.core.files.storage import FileSystemStorage
from rest_framework.decorators import api_view
from rest_framework.response import Response
from .serializers import GuardianLogSerializer
from django.db.models import OuterRef, Subquery
import re

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

def get_next_apk_version():
    latest = GuardianApkUpdate.objects.order_by('-uploaded_at').first()
    prefix = "v_1_1_"
    if latest and latest.version.startswith(prefix):
        try:
            number = int(latest.version.replace(prefix, ""))
            return f"{prefix}{number + 1}"
        except ValueError:
            pass
    return f"{prefix}1"

def log_dashboard(request):
    logs = GuardianLog.objects.select_related('device').order_by('-timestamp')[:200]
    devices = GuardianDevice.objects.all()

    # Annotate each device with latest patch info
    latest_patch_qs = GuardianPatch.objects.filter(
        device=OuterRef('pk'), active=True
    ).order_by('-uploaded_at')

    devices = devices.annotate(
        latest_patch_version=Subquery(latest_patch_qs.values('version')[:1]),
        latest_patch_time=Subquery(latest_patch_qs.values('uploaded_at')[:1])
    )

    if request.method == 'POST':
        submitted_token = request.POST.get("submit_token")

        # 1. Per-device override/apply action
        if submitted_token:
            try:
                device = GuardianDevice.objects.get(token=submitted_token)
                override_enabled = f"override_{device.token}" in request.POST
                forced_state = request.POST.get(f"force_{device.token}") == "on"

                device.override_enabled = override_enabled
                device.override_value = forced_state
                device.save()

                GuardianLog.objects.create(
                    device=device,
                    log_text=f"🛰️ Remote override {'ENABLED' if override_enabled else 'DISABLED'} — State: {'ON' if forced_state else 'OFF'}"
                )
            except GuardianDevice.DoesNotExist:
                GuardianLog.objects.create(
                    device=None,
                    log_text=f"⚠️ Override failed — device not found: {submitted_token}"
                )

        # 2. Optional APK upload
        if 'upload_apk' in request.POST:
            apk_file = request.FILES.get('apk_file')
            changelog = request.POST.get('changelog', '')
            version = request.POST.get('version') or get_next_apk_version()

            if apk_file:
                GuardianApkUpdate.objects.all().update(active=False)
                GuardianApkUpdate.objects.create(
                    apk_file=apk_file,
                    version=version,
                    changelog=changelog,
                    active=True
                )
                GuardianLog.objects.create(
                    device=None,
                    log_text=f"📦 New APK v{version} uploaded to dashboard"
                )

        return redirect('guardian-log-dashboard')

    return render(request, 'guardian/dashboard.html', {
        'logs': logs,
        'devices': devices,
        'latest_apk': GuardianApkUpdate.objects.filter(active=True).first()
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

def get_patch_url(request, token):
    device = get_object_or_404(GuardianDevice, token=token)
    patch = GuardianPatch.objects.filter(device=device, active=True).first()
    if patch:
        return JsonResponse({'patch_url': patch.dex_file.url})
    return JsonResponse({'patch_url': None})

@csrf_exempt
def upload_patch_file(request):
    if request.method == 'POST':
        token = request.POST.get('device_token')
        version = request.POST.get('version')
        patch_file = request.FILES.get('dex_patch')

        if not (token and version and patch_file):
            return JsonResponse({'error': 'Missing required fields'}, status=400)

        device = get_object_or_404(GuardianDevice, token=token)

        # Mark previous patches inactive
        GuardianPatch.objects.filter(device=device).update(active=False)

        new_patch = GuardianPatch.objects.create(
            device=device,
            version=version,
            dex_file=patch_file,
            active=True
        )

        GuardianLog.objects.create(
            device=device,
            log_text=f"✨ New patch uploaded: v{version}"
        )

        return JsonResponse({'message': f"Patch v{version} uploaded successfully"})

    return JsonResponse({'error': 'Invalid method'}, status=405)
