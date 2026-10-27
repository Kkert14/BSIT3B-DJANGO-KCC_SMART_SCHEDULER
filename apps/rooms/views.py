from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
from django.db.models import Q
from django.db import IntegrityError

from apps.building.models import Building
from .models import Room
from apps.users.decorators import admin_required, admin_required_api
from apps.utils.import_export import (
    excel_to_dict_list,
    get_str,
    get_value,
    parse_bool,
    parse_time,
    queryset_to_excel,
    workbook_to_response,
)


@login_required(login_url='login')
def room_list_page(request):
    query = request.GET.get('q', '').strip()
    rooms_list = Room.objects.select_related('building').all()
    if query:
        rooms_list = rooms_list.filter(
            Q(room_name__icontains=query) |
            Q(building__code__icontains=query) |
            Q(building__name__icontains=query) |
            Q(room_type__icontains=query)
        )
    paginator = Paginator(rooms_list, 10)
    page_number = request.GET.get('page', 1)
    rooms = paginator.get_page(page_number)
    buildings = Building.objects.filter(is_active=True).order_by('code')
    return render(request, 'room_list.html', {
        'rooms': rooms,
        'query': query,
        'buildings': buildings,
    })


@login_required(login_url='login')
def room_list_ajax(request):
    query = request.GET.get('q', '').strip()
    rooms_list = Room.objects.select_related('building').all()
    if query:
        rooms_list = rooms_list.filter(
            Q(room_name__icontains=query) |
            Q(building__code__icontains=query) |
            Q(building__name__icontains=query) |
            Q(room_type__icontains=query)
        )
    paginator = Paginator(rooms_list, 10)
    page_number = request.GET.get('page', 1)
    rooms = paginator.get_page(page_number)
    data = list(rooms.object_list.values(
        'id', 'room_name', 'room_type', 'capacity', 'is_active', 'building_id',
    ))
    for item in data:
        building = Building.objects.filter(pk=item.pop('building_id')).first()
        item['building'] = str(building) if building else ''
    return JsonResponse({
        'data': data,
        'has_next': rooms.has_next(),
        'has_prev': rooms.has_previous(),
        'page': rooms.number,
        'pages': rooms.paginator.num_pages,
        'total': rooms.paginator.count,
    })


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


@login_required(login_url='login')
@admin_required
def room_export_excel(request):
    rooms = Room.objects.select_related('building').all().order_by('building__code', 'room_name')
    wb = queryset_to_excel(
        rooms,
        ['building__code', 'room_name', 'room_type', 'capacity', 'is_active'],
        sheet_name='Rooms',
        title='Rooms Export',
    )
    return workbook_to_response(wb, 'rooms_export.xlsx')


@admin_required_api
@login_required(login_url='login')
@require_POST
def room_import_excel(request):
    if 'file' not in request.FILES:
        return JsonResponse({'error': 'No file uploaded.'}, status=400)

    uploaded_file = request.FILES['file']
    try:
        data = excel_to_dict_list(uploaded_file.read())
    except Exception as e:
        return JsonResponse({'error': f'Failed to read file: {str(e)}'}, status=400)

    created = 0
    errors = []
    for idx, row in enumerate(data, start=2):
        building_code = get_str(row, 'building_code')
        room_name = get_str(row, 'room_name')
        room_type = get_str(row, 'room_type', 'Classroom')
        capacity = get_str(row, 'capacity')
        is_active = parse_bool(get_value(row, 'is_active'))

        if not building_code or not room_name:
            errors.append(f'Row {idx}: building_code and room_name are required.')
            continue

        try:
            building = Building.objects.get(code=building_code)
        except Building.DoesNotExist:
            errors.append(f'Row {idx}: building with code "{building_code}" not found.')
            continue

        try:
            capacity_val = int(capacity) if capacity else 1
        except ValueError:
            errors.append(f'Row {idx}: capacity must be a number.')
            continue

        try:
            room, created_flag = Room.objects.update_or_create(
                building=building,
                room_name=room_name,
                defaults={'room_type': room_type, 'capacity': capacity_val, 'is_active': is_active},
            )
            if created_flag:
                created += 1
        except Exception as e:
            errors.append(f'Row {idx}: {str(e)}')

    return JsonResponse({
        'status': 'success',
        'created': created,
        'errors': errors,
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
