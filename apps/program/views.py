from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
from django.db.models import Q
from django.db import IntegrityError

from .models import Program
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
def program_list_page(request):
    query = request.GET.get('q', '').strip()
    programs_list = Program.objects.all()
    if query:
        programs_list = programs_list.filter(
            Q(program_code__icontains=query) | Q(program_description__icontains=query)
        )
    paginator = Paginator(programs_list, 10)
    page_number = request.GET.get('page', 1)
    programs = paginator.get_page(page_number)
    return render(request, 'program_list.html', {
        'programs': programs,
        'query': query,
    })


@login_required(login_url='login')
def program_list_ajax(request):
    query = request.GET.get('q', '').strip()
    programs_list = Program.objects.all()
    if query:
        programs_list = programs_list.filter(
            Q(program_code__icontains=query) | Q(program_description__icontains=query)
        )
    paginator = Paginator(programs_list, 10)
    page_number = request.GET.get('page', 1)
    programs = paginator.get_page(page_number)
    data = list(programs.object_list.values('id', 'program_code', 'program_description', 'is_active'))
    return JsonResponse({
        'data': data,
        'has_next': programs.has_next(),
        'has_prev': programs.has_previous(),
        'page': programs.number,
        'pages': programs.paginator.num_pages,
        'total': programs.paginator.count,
    })


@login_required(login_url='login')
def program_get_ajax(request, pk):
    program = get_object_or_404(Program, pk=pk)
    return JsonResponse({
        'id': program.id,
        'program_code': program.program_code,
        'program_description': program.program_description,
        'is_active': program.is_active,
    })


@admin_required_api
@login_required(login_url='login')
@require_POST
def program_save_ajax(request):
    program_id = request.POST.get('id')
    if program_id:
        program = get_object_or_404(Program, pk=program_id)
    else:
        program = Program()

    program_code = request.POST.get('program_code', '').strip()
    program_description = request.POST.get('program_description', '').strip()
    is_active = request.POST.get('is_active') == 'true'

    if not program_code:
        return JsonResponse({'error': 'Program code is required.'}, status=400)
    if not program_description:
        return JsonResponse({'error': 'Program description is required.'}, status=400)

    dup_qs = Program.objects.filter(Q(program_code=program_code) | Q(program_description=program_description))
    if program_id:
        dup_qs = dup_qs.exclude(pk=program_id)
    if dup_qs.filter(program_code=program_code).exists():
        return JsonResponse({'error': 'That program code is already taken.'}, status=400)
    if dup_qs.filter(program_description=program_description).exists():
        return JsonResponse({'error': 'That program description is already in use.'}, status=400)

    program.program_code = program_code
    program.program_description = program_description
    program.is_active = is_active

    try:
        program.save()
    except IntegrityError:
        return JsonResponse({'error': 'Could not save program due to a conflict.'}, status=400)

    messages.success(request, f'Program "{program.program_code}" has been saved successfully.')
    return JsonResponse({
        'status': 'success',
        'id': program.id,
        'program_code': program.program_code,
        'program_description': program.program_description,
        'is_active': program.is_active,
    })


@login_required(login_url='login')
@admin_required
def program_export_excel(request):
    programs = Program.objects.all().order_by('program_code')
    wb = queryset_to_excel(
        programs,
        ['program_code', 'program_description', 'is_active'],
        sheet_name='Programs',
        title='Programs Export',
    )
    return workbook_to_response(wb, 'programs_export.xlsx')


@admin_required_api
@login_required(login_url='login')
@require_POST
def program_import_excel(request):
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
        program_code = get_str(row, 'program_code')
        program_description = get_str(row, 'program_description')
        is_active = parse_bool(get_value(row, 'is_active'))

        if not program_code or not program_description:
            errors.append(f'Row {idx}: program_code and program_description are required.')
            continue

        try:
            program, created_flag = Program.objects.update_or_create(
                program_code=program_code,
                defaults={'program_description': program_description, 'is_active': is_active},
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
def program_delete_ajax(request, pk):
    program = get_object_or_404(Program, pk=pk)
    program_code = program.program_code
    program.delete()
    messages.success(request, f'Program "{program_code}" has been deleted successfully.')
    return JsonResponse({'status': 'deleted'})
