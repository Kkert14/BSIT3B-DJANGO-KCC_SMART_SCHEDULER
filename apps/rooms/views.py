from django.shortcuts import get_object_or_404, redirect
from django.http import JsonResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.db import IntegrityError

from apps.building.models import Building
from .models import Room
from apps.users.decorators import admin_required, admin_required_api


@login_required(login_url='login')
def room_list_page(request):
    """Rooms live inside each building now; send old links there."""
    return redirect('building:building_list')



@login_required(login_url='login')
def room_get_ajax(request, pk):
    room = get_object_or_404(Room.objects.select_related('building'), pk=pk)
    return JsonResponse({
        'id': room.id,
        'building': room.building.id,
        'building_name': str(room.building),
        'room_name': room.room_name,
        'room_type': room.room_type,
        'capacity': room.capacity,
        'is_active': room.is_active,
    })


@admin_required_api
@login_required(login_url='login')
@require_POST
def room_save_ajax(request):
    room_id = request.POST.get('id')
    if room_id:
        room = get_object_or_404(Room, pk=room_id)
    else:
        room = Room()

    building_id = request.POST.get('building')
    room_name = request.POST.get('room_name', '').strip()
    room_type = request.POST.get('room_type', 'Classroom').strip()
    capacity = request.POST.get('capacity', '').strip()
    is_active = request.POST.get('is_active') == 'true'

    if not building_id:
        return JsonResponse({'error': 'Building is required.'}, status=400)
    try:
        building = Building.objects.get(pk=int(building_id))
    except (Building.DoesNotExist, ValueError, TypeError):
        return JsonResponse({'error': 'Invalid building.'}, status=400)

    if not room_name:
        return JsonResponse({'error': 'Room name is required.'}, status=400)
    if not capacity:
        return JsonResponse({'error': 'Capacity is required.'}, status=400)
    try:
        capacity = int(capacity)
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Capacity must be a number.'}, status=400)

    dup_qs = Room.objects.filter(building=building, room_name=room_name)
    if room_id:
        dup_qs = dup_qs.exclude(pk=room_id)
    if dup_qs.exists():
        return JsonResponse({'error': 'A room with that name already exists in this building.'}, status=400)

    room.building = building
    room.room_name = room_name
    room.room_type = room_type
    room.capacity = capacity
    room.is_active = is_active

    try:
        room.save()
    except IntegrityError:
        return JsonResponse({'error': 'Could not save room due to a conflict.'}, status=400)

    messages.success(request, f'Room "{room.room_name}" has been saved successfully.')
    return JsonResponse({
        'status': 'success',
        'id': room.id,
        'building': room.building.id,
        'building_name': str(room.building),
        'room_name': room.room_name,
        'room_type': room.room_type,
        'capacity': room.capacity,
        'is_active': room.is_active,
    })


@admin_required_api
@login_required(login_url='login')
@require_POST
def room_delete_ajax(request, pk):
    room = get_object_or_404(Room, pk=pk)
    room_name = room.room_name
    room.delete()
    messages.success(request, f'Room "{room_name}" has been deleted successfully.')
    return JsonResponse({'status': 'deleted'})
