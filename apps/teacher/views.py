from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
from django.db.models import Q
from django.db import IntegrityError

from .models import Teacher

User = get_user_model()


@login_required(login_url='login')
def teacher_list_page(request):
    query = request.GET.get('q', '').strip()
    teachers_list = Teacher.objects.select_related('user').all()
    if query:
        teachers_list = teachers_list.filter(
            Q(employee_number__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(contact_number__icontains=query) |
            Q(user__username__icontains=query)
        )
    paginator = Paginator(teachers_list, 10)
    page_number = request.GET.get('page', 1)
    teachers = paginator.get_page(page_number)
    users = User.objects.filter(is_active=True).order_by('username')
    return render(request, 'teacher_list.html', {
        'teachers': teachers,
        'query': query,
        'users': users,
    })


@login_required(login_url='login')
def teacher_list_ajax(request):
    query = request.GET.get('q', '').strip()
    teachers_list = Teacher.objects.select_related('user').all()
    if query:
        teachers_list = teachers_list.filter(
            Q(employee_number__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(contact_number__icontains=query) |
            Q(user__username__icontains=query)
        )
    paginator = Paginator(teachers_list, 10)
    page_number = request.GET.get('page', 1)
    teachers = paginator.get_page(page_number)
    data = list(teachers.object_list.values(
        'id', 'employee_number', 'first_name', 'last_name',
        'contact_number', 'is_active', 'user_id',
    ))
    for item in data:
        user = User.objects.filter(pk=item.pop('user_id')).first()
        item['user'] = user.username if user else None
    return JsonResponse({
        'data': data,
        'has_next': teachers.has_next(),
        'has_prev': teachers.has_previous(),
        'page': teachers.number,
        'pages': teachers.paginator.num_pages,
        'total': teachers.paginator.count,
    })


@login_required(login_url='login')
def teacher_get_ajax(request, pk):
    teacher = get_object_or_404(Teacher.objects.select_related('user'), pk=pk)
    return JsonResponse({
        'id': teacher.id,
        'user': teacher.user.id if teacher.user else None,
        'employee_number': teacher.employee_number,
        'first_name': teacher.first_name,
        'last_name': teacher.last_name,
        'contact_number': teacher.contact_number,
        'is_active': teacher.is_active,
    })


@login_required(login_url='login')
@require_POST
def teacher_save_ajax(request):
    teacher_id = request.POST.get('id')
    if teacher_id:
        teacher = get_object_or_404(Teacher, pk=teacher_id)
    else:
        teacher = Teacher()

    user_id = request.POST.get('user', '').strip()
    employee_number = request.POST.get('employee_number', '').strip()
    first_name = request.POST.get('first_name', '').strip()
    last_name = request.POST.get('last_name', '').strip()
    contact_number = request.POST.get('contact_number', '').strip()
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

    dup_qs = Teacher.objects.filter(employee_number=employee_number)
    if teacher_id:
        dup_qs = dup_qs.exclude(pk=teacher_id)
    if dup_qs.exists():
        return JsonResponse({'error': 'That employee number is already taken.'}, status=400)

    if user:
        dup_qs = Teacher.objects.filter(user=user)
        if teacher_id:
            dup_qs = dup_qs.exclude(pk=teacher_id)
        if dup_qs.exists():
            return JsonResponse({'error': 'That user already has a teacher profile.'}, status=400)

    teacher.user = user
    teacher.employee_number = employee_number
    teacher.first_name = first_name
    teacher.last_name = last_name
    teacher.contact_number = contact_number
    teacher.is_active = is_active

    try:
        teacher.save()
    except IntegrityError:
        return JsonResponse({'error': 'Could not save teacher due to a conflict.'}, status=400)

    messages.success(request, f'Teacher "{teacher.first_name} {teacher.last_name}" has been saved successfully.')
    return JsonResponse({
        'status': 'success',
        'id': teacher.id,
        'user': teacher.user.id if teacher.user else None,
        'employee_number': teacher.employee_number,
        'first_name': teacher.first_name,
        'last_name': teacher.last_name,
        'contact_number': teacher.contact_number,
        'is_active': teacher.is_active,
    })


@login_required(login_url='login')
@require_POST
def teacher_delete_ajax(request, pk):
    teacher = get_object_or_404(Teacher, pk=pk)
    name = f'{teacher.first_name} {teacher.last_name}'
    teacher.delete()
    messages.success(request, f'Teacher "{name}" has been deleted successfully.')
    return JsonResponse({'status': 'deleted'})
