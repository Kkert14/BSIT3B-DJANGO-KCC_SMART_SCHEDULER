from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
from django.db.models import Q
from django.db import IntegrityError

from .models import Program


@login_required(login_url='login')
def program_list_page(request):
    query = request.GET.get('q', '').strip()
    programs_list = Program.objects.all()
    if query:
        programs_list = programs_list.filter(
            Q(code__icontains=query) | Q(name__icontains=query)
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
            Q(code__icontains=query) | Q(name__icontains=query)
        )
    paginator = Paginator(programs_list, 10)
    page_number = request.GET.get('page', 1)
    programs = paginator.get_page(page_number)
    data = list(programs.object_list.values('id', 'code', 'name', 'is_active'))
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
        'code': program.code,
        'name': program.name,
        'is_active': program.is_active,
    })


@login_required(login_url='login')
@require_POST
def program_save_ajax(request):
    program_id = request.POST.get('id')
    if program_id:
        program = get_object_or_404(Program, pk=program_id)
    else:
        program = Program()

    code = request.POST.get('code', '').strip()
    name = request.POST.get('name', '').strip()
    is_active = request.POST.get('is_active') == 'true'

    if not code:
        return JsonResponse({'error': 'Code is required.'}, status=400)
    if not name:
        return JsonResponse({'error': 'Name is required.'}, status=400)

    dup_qs = Program.objects.filter(Q(code=code) | Q(name=name))
    if program_id:
        dup_qs = dup_qs.exclude(pk=program_id)
    if dup_qs.filter(code=code).exists():
        return JsonResponse({'error': 'That program code is already taken.'}, status=400)
    if dup_qs.filter(name=name).exists():
        return JsonResponse({'error': 'That program name is already in use.'}, status=400)

    program.code = code
    program.name = name
    program.is_active = is_active

    try:
        program.save()
    except IntegrityError:
        return JsonResponse({'error': 'Could not save program due to a conflict.'}, status=400)

    messages.success(request, f'Program "{program.code}" has been saved successfully.')
    return JsonResponse({
        'status': 'success',
        'id': program.id,
        'code': program.code,
        'name': program.name,
        'is_active': program.is_active,
    })


@login_required(login_url='login')
@require_POST
def program_delete_ajax(request, pk):
    program = get_object_or_404(Program, pk=pk)
    code = program.code
    program.delete()
    messages.success(request, f'Program "{code}" has been deleted successfully.')
    return JsonResponse({'status': 'deleted'})
