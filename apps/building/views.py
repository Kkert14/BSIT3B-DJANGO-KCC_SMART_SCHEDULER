from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
from django.db.models import Q
from django.db import IntegrityError

from .models import Building
from apps.users.decorators import admin_required, admin_required_api


@login_required(login_url='login')
def building_list_page(request):
    query = request.GET.get('q', '').strip()
    buildings_list = Building.objects.all()
    if query:
        buildings_list = buildings_list.filter(
            Q(code__icontains=query) | Q(name__icontains=query)
        )
    paginator = Paginator(buildings_list, 10)
    page_number = request.GET.get('page', 1)
    buildings = paginator.get_page(page_number)
    return render(request, 'building_list.html', {
        'buildings': buildings,
        'query': query,
    })


@login_required(login_url='login')
def building_list_ajax(request):
    query = request.GET.get('q', '').strip()
    buildings_list = Building.objects.all()
    if query:
        buildings_list = buildings_list.filter(
            Q(code__icontains=query) | Q(name__icontains=query)
        )
    paginator = Paginator(buildings_list, 10)
    page_number = request.GET.get('page', 1)
    buildings = paginator.get_page(page_number)
    data = list(buildings.object_list.values('id', 'code', 'name', 'is_active'))
    return JsonResponse({
        'data': data,
        'has_next': buildings.has_next(),
        'has_prev': buildings.has_previous(),
        'page': buildings.number,
        'pages': buildings.paginator.num_pages,
        'total': buildings.paginator.count,
    })


@login_required(login_url='login')
def building_get_ajax(request, pk):
    building = get_object_or_404(Building, pk=pk)
    return JsonResponse({
        'id': building.id,
        'code': building.code,
        'name': building.name,
        'is_active': building.is_active,
    })


@admin_required_api
@login_required(login_url='login')
@require_POST
def building_save_ajax(request):
    building_id = request.POST.get('id')
    if building_id:
        building = get_object_or_404(Building, pk=building_id)
    else:
        building = Building()

    code = request.POST.get('code', '').strip()
    name = request.POST.get('name', '').strip()
    is_active = request.POST.get('is_active') == 'true'

    if not code:
        return JsonResponse({'error': 'Code is required.'}, status=400)
    if not name:
        return JsonResponse({'error': 'Name is required.'}, status=400)

    dup_qs = Building.objects.filter(Q(code=code) | Q(name=name))
    if building_id:
        dup_qs = dup_qs.exclude(pk=building_id)
    if dup_qs.filter(code=code).exists():
        return JsonResponse({'error': 'That building code is already taken.'}, status=400)
    if dup_qs.filter(name=name).exists():
        return JsonResponse({'error': 'That building name is already in use.'}, status=400)

    building.code = code
    building.name = name
    building.is_active = is_active

    try:
        building.save()
    except IntegrityError:
        return JsonResponse({'error': 'Could not save building due to a conflict.'}, status=400)

    messages.success(request, f'Building "{building.code}" has been saved successfully.')
    return JsonResponse({
        'status': 'success',
        'id': building.id,
        'code': building.code,
        'name': building.name,
        'is_active': building.is_active,
    })


@admin_required_api
@login_required(login_url='login')
@require_POST
def building_delete_ajax(request, pk):
    building = get_object_or_404(Building, pk=pk)
    code = building.code
    building.delete()
    messages.success(request, f'Building "{code}" has been deleted successfully.')
    return JsonResponse({'status': 'deleted'})


# EXPORT BUILDINGS TO EXCEL


# IMPORT BUILDINGS FROM EXCEL
