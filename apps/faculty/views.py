from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
from django.db.models import Q
from django.db import IntegrityError

from .models import Faculty
from apps.users.decorators import admin_required, admin_required_api

User = get_user_model()


@login_required(login_url='login')
def faculty_list_page(request):
    query = request.GET.get('q', '').strip()
    faculty_list = Faculty.objects.select_related('user').all()
    if query:
        faculty_list = faculty_list.filter(
            Q(employee_number__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(email__icontains=query) |
            Q(position__icontains=query) |
            Q(user__username__icontains=query)
        )
    paginator = Paginator(faculty_list, 10)
    page_number = request.GET.get('page', 1)
    faculty = paginator.get_page(page_number)
    users = User.objects.filter(is_active=True).order_by('username')
    return render(request, 'faculty_list.html', {
        'faculty': faculty,
        'query': query,
        'users': users,
    })


@login_required(login_url='login')
def faculty_list_ajax(request):
    query = request.GET.get('q', '').strip()
    faculty_list = Faculty.objects.select_related('user').all()
    if query:
        faculty_list = faculty_list.filter(
            Q(employee_number__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(email__icontains=query) |
            Q(position__icontains=query) |
            Q(user__username__icontains=query)
        )
    paginator = Paginator(faculty_list, 10)
    page_number = request.GET.get('page', 1)
    faculty = paginator.get_page(page_number)
    data = list(faculty.object_list.values(
        'id', 'employee_number', 'first_name', 'last_name',
        'email', 'position', 'is_active', 'user_id',
    ))
    for item in data:
        user = User.objects.filter(pk=item.pop('user_id')).first()
        item['user'] = user.username if user else None
    return JsonResponse({
        'data': data,
        'has_next': faculty.has_next(),
        'has_prev': faculty.has_previous(),
        'page': faculty.number,
        'pages': faculty.paginator.num_pages,
        'total': faculty.paginator.count,
    })


@login_required(login_url='login')
def faculty_get_ajax(request, pk):
    faculty_member = get_object_or_404(Faculty.objects.select_related('user'), pk=pk)
    return JsonResponse({
        'id': faculty_member.id,
        'user': faculty_member.user.id if faculty_member.user else None,
        'employee_number': faculty_member.employee_number,
        'first_name': faculty_member.first_name,
        'last_name': faculty_member.last_name,
        'email': faculty_member.email,
        'position': faculty_member.position,
        'is_active': faculty_member.is_active,
    })


@admin_required_api
@login_required(login_url='login')
@require_POST
def faculty_save_ajax(request):
    faculty_id = request.POST.get('id')
    if faculty_id:
        faculty_member = get_object_or_404(Faculty, pk=faculty_id)
    else:
        faculty_member = Faculty()

    user_id = request.POST.get('user', '').strip()
    employee_number = request.POST.get('employee_number', '').strip()
    first_name = request.POST.get('first_name', '').strip()
    last_name = request.POST.get('last_name', '').strip()
    email = request.POST.get('email', '').strip()
    position = request.POST.get('position', '').strip()
    is_active = request.POST.get('is_active') == 'true'

    if not employee_number:
        return JsonResponse({'error': 'Employee number is required.'}, status=400)
    if not first_name:
        return JsonResponse({'error': 'First name is required.'}, status=400)
    if not last_name:
        return JsonResponse({'error': 'Last name is required.'}, status=400)

    user = None
    if user_id:
        try:
            user = User.objects.get(pk=int(user_id))
        except (User.DoesNotExist, ValueError, TypeError):
            return JsonResponse({'error': 'Invalid user account.'}, status=400)

    dup_qs = Faculty.objects.filter(employee_number=employee_number)
    if faculty_id:
        dup_qs = dup_qs.exclude(pk=faculty_id)
    if dup_qs.exists():
        return JsonResponse({'error': 'That employee number is already taken.'}, status=400)

    if user:
        dup_qs = Faculty.objects.filter(user=user)
        if faculty_id:
            dup_qs = dup_qs.exclude(pk=faculty_id)
        if dup_qs.exists():
            return JsonResponse({'error': 'That user already has a faculty profile.'}, status=400)

    faculty_member.user = user
    faculty_member.employee_number = employee_number
    faculty_member.first_name = first_name
    faculty_member.last_name = last_name
    faculty_member.email = email
    faculty_member.position = position
    faculty_member.is_active = is_active

    try:
        faculty_member.save()
    except IntegrityError:
        return JsonResponse({'error': 'Could not save faculty due to a conflict.'}, status=400)

    messages.success(
        request,
        f'Faculty "{faculty_member.first_name} {faculty_member.last_name}" has been saved successfully.',
    )
    return JsonResponse({
        'status': 'success',
        'id': faculty_member.id,
        'user': faculty_member.user.id if faculty_member.user else None,
        'employee_number': faculty_member.employee_number,
        'first_name': faculty_member.first_name,
        'last_name': faculty_member.last_name,
        'email': faculty_member.email,
        'position': faculty_member.position,
        'is_active': faculty_member.is_active,
    })


@admin_required_api
@login_required(login_url='login')
@require_POST
def faculty_delete_ajax(request, pk):
    faculty_member = get_object_or_404(Faculty, pk=pk)
    name = f'{faculty_member.first_name} {faculty_member.last_name}'
    faculty_member.delete()
    messages.success(request, f'Faculty "{name}" has been deleted successfully.')
    return JsonResponse({'status': 'deleted'})
