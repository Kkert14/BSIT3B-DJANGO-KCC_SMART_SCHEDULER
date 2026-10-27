from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.contrib import messages
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.db.models import Q

from apps.users.decorators import admin_required, admin_required_api
from apps.users.models import UserProfile
from apps.utils.import_export import (
    excel_to_dict_list,
    get_str,
    get_value,
    parse_bool,
    parse_time,
    queryset_to_excel,
    workbook_to_response,
)


# PAGE
@login_required(login_url='login')
@admin_required
def user_list_page(request):
    query = request.GET.get('q', '').strip()

    users_list = User.objects.select_related('profile').all().order_by('-date_joined')

    if query:
        users_list = users_list.filter(
            Q(username__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(email__icontains=query)
        )

    paginator = Paginator(users_list, 10)
    page_number = request.GET.get('page', 1)
    users = paginator.get_page(page_number)

    return render(request, 'users/list.html', {
        'users': users,
        'query': query,
    })


# LIST USERS (AJAX)
@admin_required_api
@login_required(login_url='login')
def user_list_ajax(request):
    users_list = User.objects.select_related('profile').all().order_by('-date_joined')
    paginator = Paginator(users_list, 10)
    page_number = request.GET.get('page', 1)
    users = paginator.get_page(page_number)
    data = list(users.object_list.values(
        'id',
        'username',
        'first_name',
        'last_name',
        'email',
        'is_staff',
        'is_active',
        'date_joined',
        'profile__role',
    ))
    return JsonResponse({
        "data":     data,
        "has_next": users.has_next(),
        "has_prev": users.has_previous(),
        "page":     users.number,
        "pages":    users.paginator.num_pages,
        "total":    users.paginator.count,
    })


# GET SINGLE USER (AJAX)
@admin_required_api
@login_required(login_url='login')
def user_get_ajax(request, pk):
    user = get_object_or_404(User.objects.select_related('profile'), pk=pk)
    return JsonResponse({
        "id":         user.id,
        "username":   user.username,
        "first_name": user.first_name,
        "last_name":  user.last_name,
        "email":      user.email,
        "is_staff":   user.is_staff,
        "is_active":  user.is_active,
        "role":       user.profile.role if hasattr(user, 'profile') else 'student',
    })


# CREATE / UPDATE USER (AJAX)
@admin_required_api
@login_required(login_url='login')
@require_POST
def user_save_ajax(request):
    user_id = request.POST.get("id")

    if user_id:
        user = get_object_or_404(User, pk=user_id)
        is_update = True
    else:
        user = User()
        is_update = False

    username = request.POST.get("username", "").strip()
    email = request.POST.get("email", "").strip()
    role = request.POST.get("role", "student").strip()

    if not username:
        return JsonResponse({"error": "Username is required."}, status=400)

    dup_qs = User.objects.filter(Q(username=username) | (Q(email=email) & ~Q(email="")))
    if user_id:
        dup_qs = dup_qs.exclude(pk=user_id)
    if dup_qs.filter(username=username).exists():
        return JsonResponse({"error": "That username is already taken."}, status=400)
    if email and dup_qs.filter(email=email).exists():
        return JsonResponse({"error": "That email is already in use."}, status=400)

    user.username   = username
    user.first_name = request.POST.get("first_name", "")
    user.last_name  = request.POST.get("last_name", "")
    user.email      = email
    user.is_staff   = request.POST.get("is_staff") == "true"
    user.is_active  = request.POST.get("is_active") == "true"

    password = request.POST.get("password")
    if password:
        user.set_password(password)
    elif not user_id:
        return JsonResponse({"error": "Password is required for new users."}, status=400)

    try:
        user.save()
    except IntegrityError:
        return JsonResponse({"error": "Could not save user due to a conflict (duplicate username/email)."}, status=400)

    # Save/update user profile role
    profile, created = UserProfile.objects.get_or_create(
        user=user,
        defaults={'role': role},
    )
    if not created:
        profile.role = role
        profile.save()

    messages.success(
        request,
        f'User "{user.username}" has been {"updated" if is_update else "saved"} successfully.'
    )

    return JsonResponse({
        "status": "success",
        "id": user.id,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.email,
        "is_staff": user.is_staff,
        "is_active": user.is_active,
        "role": profile.role,
    })


# DELETE USER (AJAX)
@admin_required_api
@login_required(login_url='login')
@require_POST
def user_delete_ajax(request, pk):
    user = get_object_or_404(User, pk=pk)
    if request.user == user:
        return JsonResponse({"error": "You cannot delete yourself"}, status=400)
    username = user.username
    user.delete()
    return JsonResponse({
        "status": "deleted",
        "message": f'User "{username}" has been deleted successfully.',
    })


# EXPORT USERS TO EXCEL
@login_required(login_url='login')
@admin_required
def user_export_excel(request):
    users = User.objects.select_related('profile').all().order_by('username')
    wb = queryset_to_excel(
        users,
        ['username', 'first_name', 'last_name', 'email', 'profile__role', 'is_active', 'date_joined'],
        sheet_name='Users',
        title='Users Export',
    )
    return workbook_to_response(wb, 'users_export.xlsx')


# IMPORT USERS FROM EXCEL
@admin_required_api
@login_required(login_url='login')
@require_POST
def user_import_excel(request):
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
        username = get_str(row, 'username')
        first_name = get_str(row, 'first_name')
        last_name = get_str(row, 'last_name')
        email = get_str(row, 'email')
        role = get_str(row, 'profile__role', 'student')
        is_active = parse_bool(get_value(row, 'is_active'))

        if not username:
            errors.append(f'Row {idx}: username is required.')
            continue

        try:
            user, created_flag = User.objects.update_or_create(
                username=username,
                defaults={
                    'first_name': first_name,
                    'last_name': last_name,
                    'email': email,
                    'is_active': is_active,
                },
            )
            if created_flag:
                user.set_password('changeme123')  # Default password
                user.save()
                created += 1

            # Save/update user profile role
            profile, _ = UserProfile.objects.update_or_create(
                user=user,
                defaults={'role': role},
            )
        except Exception as e:
            errors.append(f'Row {idx}: {str(e)}')

    return JsonResponse({
        'status': 'success',
        'created': created,
        'errors': errors,
    })
