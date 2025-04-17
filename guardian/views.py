from .models import GuardianControl, GuardianLog, GuardianDevice

from django.shortcuts import render
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
