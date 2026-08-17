from django.shortcuts import render, redirect

from core import settings
from itertools import chain

from .models import Task, Complaint, SubTask, Notification
from .forms import TaskForm
from django.db.models import Sum
from django.utils.decorators import method_decorator
from django.db.models.functions import Coalesce
from decimal import Decimal
import json
import logging
from groq import Groq
import csv
import threading
from dotenv import load_dotenv
import requests
import json
from django.contrib.auth.views import LoginView
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.db import models
from .models import MaintenanceWorkItem
from django.http import JsonResponse
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.db.models.functions import TruncMonth
from django.db.models.functions import TruncMonth, Extract
from django.db.models import Sum, Count, Case, When, IntegerField, Avg, F, ExpressionWrapper, DurationField
from django.contrib.auth.models import User
from django.views.decorators.csrf import csrf_exempt
import os
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404
from django.utils import timezone
from datetime import datetime, timedelta
from django.contrib import messages
from .models import TaskAttachment,MaterialRequest,RequestedMaterialItem  # Ensure you import this at the top
import uuid
from .models import Profile
import pytz  # Import pytz
from .forms import (
    TaskForm,
    ComplaintForm,
    SubTaskForm
)
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.http import JsonResponse
from .models import MaintenanceWorkItem

from django.http import JsonResponse
from .models import MaintenanceWorkItem

from .serializers import TaskSerializer
from django.db.models import Sum
from .models import Task, Complaint, SubTask, Notification, Profile, TaskItem
from deep_translator import GoogleTranslator
from .notifications import send_telegram_msg


def translate_to_english(text):
    if not text or not text.strip():
        return text
    try:
        # Detects language automatically and translates to English
        return GoogleTranslator(source='auto', target='en').translate(text)
    except Exception as e:
        print(f"Translation error: {e}")
        return text  # Return original if translation fails


def home(request):
    return redirect('dashboard')


def is_admin(user):
    return hasattr(user, "profile") and user.profile.role == "Admin"


@login_required
def task_list(request):
    user = request.user

    project_types = MaintenanceWorkItem.PROJECT_TYPE_CHOICES
    # 1. FIXED ROLE CHECKING
    # Try every possible way to find the user's role string.
    user_role = getattr(user, 'role', None)
    if not user_role and hasattr(user, 'profile'):
        user_role = getattr(user.profile, 'role', None)

        # If the user is a Superuser, or has an explicit Admin/Supervisor role,
        # OR if they belong to a Django Group named Admin/Supervisor:
        # UPDATED: Admin/Supervisor logic
        if user.is_superuser or user.is_staff or user_role in ['Admin'] or \
                user.groups.filter(name__in=['Admin']).exists():
            tasks = Task.objects.all()
        else:
            # UPDATED: Many-to-Many filter
            # Django automatically checks if 'user' is in the 'assigned_technicians' set
            tasks = Task.objects.filter(assigned_technicians=user)

        check_and_update_overdue_tasks(tasks)

    # FILTERS FROM URL
    status = request.GET.get('status')
    project_type = request.GET.get('project_type')
    completed_at = request.GET.get('completed_at')
    job_id = request.GET.get('job_id')

    if job_id:
        tasks = tasks.filter(job_id__icontains=job_id)

    if completed_at:
        selected_date = datetime.strptime(completed_at, '%Y-%m-%d')

        next_day = selected_date + timedelta(days=1)

        tasks = tasks.filter(
            completed_at__gte=selected_date,
            completed_at__lt=next_day
        )

    if status:
        tasks = tasks.filter(status=status)

    if project_type:
        tasks = tasks.filter(project_type=project_type)

    pending_tasks = tasks.filter(Q(status='Pending') | Q(status='Pending(قيد الانتظار)')).order_by('-created_at')
    active_tasks = tasks.filter(Q(status='In Progress') | Q(status='قيد التنفيذ')).order_by('-created_at')
    completed_tasks = tasks.filter(Q(status='Completed') | Q(status='مكتمل')).order_by('-completed_at')
    overdue_tasks = tasks.filter(status='Overdue').order_by(
        '-deadline')  # Assuming you want the closest deadline or oldest overdue

    context = {
        'project_types': project_types,
        'pending_tasks': pending_tasks,
        'active_tasks': active_tasks,
        'completed_tasks': completed_tasks,
        'overdue_tasks': overdue_tasks,
        'tasks': tasks,
    }

    return render(request, 'tasks/task_list.html', context)


@login_required
def create_task(request):
    user = request.user
    user_role = getattr(user.profile, 'role', None)
    is_admin = user.is_superuser or user.groups.filter(name="Admin").exists()

    if request.method == 'POST':
        post_data = request.POST.copy()

        # Set default priority if missing or if user is a Technician
        if user_role == 'Technician' or not post_data.get('priority'):
            post_data['priority'] = 'Medium'

        form = TaskForm(post_data, request.FILES)

        if form.is_valid():
            task = form.save(commit=False)
            now = timezone.now()

            if task.status == 'In Progress' and not task.started_at:
                task.started_at = now

            task.start_date = now
            if not task.deadline:
                task.deadline = now + timedelta(days=4)

            # Translation block
            translator = GoogleTranslator(source='auto', target='en')
            if task.description:
                try:
                    task.description = translator.translate(task.description)
                except Exception as e:
                    print(f"Description translation error: {e}")

            sub_categories = request.POST.getlist('sub_category[]')
            quantities = request.POST.getlist('quantity[]')
            translated_subs = []
            translated_qtys = []

            # Translate dynamic arrays safely
            for i, sub in enumerate(sub_categories):
                raw_qty = quantities[i] if i < len(quantities) else "0"

                if sub and sub.strip():
                    try:
                        translated_subs.append(translator.translate(sub.strip()))
                    except Exception:
                        translated_subs.append(sub.strip())

                clean_qty = str(raw_qty).strip()
                if clean_qty and not clean_qty.isdigit():
                    try:
                        translated_qtys.append(translator.translate(clean_qty))
                    except Exception:
                        translated_qtys.append(clean_qty)
                else:
                    translated_qtys.append(clean_qty if clean_qty else "0")

            # Determine Technician assignments
            tech_ids = request.POST.getlist('technicians')
            if not tech_ids and user_role == 'Technician':
                tech_ids = [user.id]

            # ---------------------------------------------------------
            # AUTO-TITLE GENERATION
            # Format: subcategory-quantity-location-unit-assigned to
            # ---------------------------------------------------------
            first_sub = translated_subs[0] if translated_subs else "General"
            first_qty = translated_qtys[0] if translated_qtys else "0"
            building = str(task.building) if task.building else "No Building"
            unit = str(task.unit) if task.unit else "No Unit"

            first_tech = User.objects.filter(id__in=tech_ids).first()
            assigned_to = first_tech.username if first_tech else "Unassigned"

            # Extract project_type from POST, GET, or existing task attribute
            project_type_val = request.POST.get('project_type') or request.GET.get('project_type') or getattr(task,
                                                                                                              'project_type',
                                                                                                              'General')
            project_type = str(project_type_val).strip() if project_type_val else "General"

            task.title = f"{building}-{unit}-{project_type}"[:200]

            # Save the task and the ManyToMany relationships
            task.save()
            task.assigned_technicians.set(tech_ids)

            # Save uploaded images once
            for img in request.FILES.getlist('task_images'):
                TaskAttachment.objects.create(task=task, image=img, uploaded_by=user)

            # Save task items
            for sub, qty in zip(translated_subs, translated_qtys):
                if sub:
                    TaskItem.objects.create(task=task, sub_category=sub, quantity=qty)

            # Send Telegram Notifications
            for tech in task.assigned_technicians.all():
                if hasattr(tech, 'profile') and tech.profile.telegram_chat_id:
                    msg = f"New Task: {task.title}\nBuilding: {building}\nCheck your dashboard."
                    try:
                        send_telegram_msg(tech.profile.telegram_chat_id, msg)
                    except Exception as e:
                        print(f"Telegram sending error: {e}")

            messages.success(request, "Task saved successfully.")
            return redirect('dashboard')

        else:
            print("❌ FORM ERRORS:", form.errors)

    else:
        # GET request handling
        dubai_tz = pytz.timezone('Asia/Dubai')
        now_dubai = timezone.now().astimezone(dubai_tz)
        deadline_dubai = now_dubai + timedelta(days=4)

        form = TaskForm(initial={
            'start_date': now_dubai.strftime('%Y-%m-%dT%H:%M'),
            'deadline': deadline_dubai.strftime('%Y-%m-%dT%H:%M')
        })

    # Pass context data to the template
    technicians = User.objects.filter(profile__role='Technician')
    all_maintenance_items = MaintenanceWorkItem.objects.all()

    return render(request, 'tasks/create_task.html', {
        'form': form,
        'technicians': technicians,
        'project_types': MaintenanceWorkItem.PROJECT_TYPE_CHOICES,
        'all_maintenance_items': all_maintenance_items,
    })


# Update your view logic to this:
@login_required
def award_reward_points_ajax(request, task_id):
    # 1. Ensure method is POST
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method.'}, status=405)

    # 2. Permissions check (Reuse your existing logic)
    task = get_object_or_404(Task, id=task_id)
    is_admin = request.user.is_superuser or (hasattr(request.user, 'profile') and request.user.profile.role == 'Admin')
    if not is_admin:
        return JsonResponse({'status': 'error', 'message': 'Unauthorized.'}, status=403)

    # 3. Process Input (Supports standard form POST data)
    # Using request.POST.get helps this work with both standard forms and FormData
    submitted_points = request.POST.get('points_awarded')

    try:
        if not submitted_points or submitted_points.strip() == '':
            task.reward_points_awarded = 0
            task.is_rewarded = False
        else:
            points = int(submitted_points)
            if points < 0:
                return JsonResponse({'status': 'error', 'message': 'Negative points.'}, status=400)

            task.reward_points_awarded = points
            task.is_rewarded = True  # Mark as rewarded

        task.save()

        # Return success with the updated state for the frontend
        return JsonResponse({
            'status': 'success',
            'message': 'Updated!',
            'points': task.reward_points_awarded,
            'is_rewarded': task.is_rewarded
        })


    except (ValueError, TypeError):
        return JsonResponse({'status': 'error', 'message': 'Invalid number format.'}, status=400)


@login_required
def start_task(request, task_id):
    task = get_object_or_404(Task, id=task_id)

    task.status = 'In Progress'
    task.started_at = timezone.now()
    task.save()
    return redirect('dashboard')


def send_task_to_google_sheet(task):
    GOOGLE_SCRIPT_WEBAPP_URL = "https://script.google.com/macros/s/AKfycbyh__GAWU2yeDBLsSFT2dIvP-CZpCASVCvPptaZm1RQ8fQD7z8lV-gx4LXdolh3d6Fn/exec"

    # --- 1. Generate itemsStr just like your JS loop does ---
    item_data = []
    for item in task.items.all():
        item_data.append(f"{item.sub_category}({item.quantity})")
    items_str = ", ".join(item_data) if item_data else "-"

    # --- 2. Generate techString matching your JS logic ---
    tech_names = [tech.username for tech in task.assigned_technicians.all()]
    tech_string = ", ".join(tech_names) if tech_names else "Unassigned"

    # --- 3. Extract the last complaint message entry ---
    last_complaint = task.complaint_set.last()
    complaint_msg = last_complaint.message if last_complaint else "No complaints"

    # --- 4. Map the payload to perfectly match your data logging sequence ---
    payload = {
        "job_id": str(task.job_id),
        "title": str(task.title or ""),
        "project_type": str(task.project_type or ""),
        "description": str(task.description or ""),
        "items": items_str,  # Populated text instead of the Manager object!
        "assigned_to": tech_string,  # Populated text instead of the Manager object!
        "budget": str(task.budget or "0.00"),
        "completed_at": task.completed_at.strftime('%d/%m/%Y %H:%M') if task.completed_at else "",
        "complaints": str(complaint_msg),
        "location": str(task.location or ""),
        "time_taken": str(task.time_taken or "")
    }

    try:
        response = requests.post(
            GOOGLE_SCRIPT_WEBAPP_URL,
            data=json.dumps(payload),
            headers={'Content-Type': 'application/json'},
            timeout=5
        )
    except requests.exceptions.RequestException as e:
        print(f"Google Sheet Sync Error: {e}")


@login_required
def end_task(request, task_id):
    task = get_object_or_404(Task, id=task_id)

    if request.method == 'POST':
        # Get the budget from the modal input
        final_budget = request.POST.get('final_budget')
        if final_budget:
            task.budget = final_budget

            # 2. Save Image if uploaded
            image = request.FILES.get('task_image')
            video = request.FILES.get('task_video')
            if image or video:
                TaskAttachment.objects.create(
                    task=task,
                    image=image,
                    video=video,
                    uploaded_by=request.user
                )

    task.status = 'Completed'
    task.completed_at = timezone.now()
    task.save()

    # Trigger the Free Google Sheet Sync webhook routine stream asynchronously
    send_task_to_google_sheet(task)
    return redirect('dashboard')


@login_required
def dashboard(request):
    # Intercept the specific user
    if request.user.username == 'approval_admin':
        return redirect('approved_materials_list')
    user = request.user
    project_types = MaintenanceWorkItem.PROJECT_TYPE_CHOICES

    # 1. Check user roles dynamically
    user_role = getattr(user, 'role', None)
    if not user_role and hasattr(user, 'profile'):
        user_role = getattr(user.profile, 'role', None)

    # 2. Base QuerySet with prefetch_related
    # PREFETCH is critical here so the template can see the assigned technicians
    base_queryset = Task.objects.prefetch_related('assigned_technicians')

    # 3. Logic for Admin vs Technicians
    if user.is_superuser or \
            user.is_staff or \
            user_role in ["Admin"] or \
            user.groups.filter(name__in=["Admin"]).exists():
        tasks = base_queryset.all()
    else:
        # Filter tasks where the user is one of the assigned technicians
        tasks = base_queryset.filter(assigned_technicians=user)

    check_and_update_overdue_tasks(tasks)

    # 4. Filtering logic
    user_filter = request.GET.get('user')
    status = request.GET.get('status')
    project_type = request.GET.get('project_type')
    completed_at = request.GET.get('completed_at')

    if status:
        tasks = tasks.filter(status=status)
    if project_type:
        tasks = tasks.filter(project_type=project_type)
    if completed_at:
        try:
            selected_date = datetime.strptime(completed_at, '%Y-%m-%d')
            next_day = selected_date + timedelta(days=1)
            tasks = tasks.filter(completed_at__gte=selected_date, completed_at__lt=next_day)
        except ValueError:
            pass  # Ignore invalid date formats

    if user_filter:
        # We filter the 'tasks' queryset to only include those
        # where an assigned technician's username matches the search
        tasks = tasks.filter(assigned_technicians__username__icontains=user_filter.strip()).distinct()
    # 5. Categorize tasks
    # Using 'distinct()' is good practice when filtering ManyToMany fields
    # to avoid duplicate task objects in the list
    # 5. Categorize tasks
    # We use order_by('-created_at') to ensure the newest ones appear first.
    # (Ensure 'created_at' exists in your Task model, otherwise use '-id')

    pending_tasks = tasks.filter(
        Q(status__in=['Pending', 'Pending(قيد الانتظار)']) |
        (Q(status='Overdue') & Q(started_at__isnull=True))
    ).distinct().order_by('-created_at')

    active_tasks = tasks.filter(
        Q(status__in=['In Progress', 'قيد التنفيذ']) |
        (Q(status='Overdue') & Q(started_at__isnull=False))
    ).distinct().order_by('-created_at')
    completed_tasks = tasks.filter(status='Completed').distinct().order_by('-completed_at')  # Newest completions first
    overdue_tasks = tasks.filter(status='Overdue').distinct().order_by('deadline')  # Closest to deadline first

    context = {
        'project_types': project_types,
        'pending_tasks': pending_tasks,
        'active_tasks': active_tasks,
        'completed_tasks': completed_tasks,
        'overdue_tasks': overdue_tasks,
        'tasks': tasks
    }

    return render(request, 'tasks/task_list.html', context)


@login_required
def task_detail(request, task_id):
    # 1. UPDATED: Visibility restriction for Technicians
    # We check if the current user is in the assigned_technicians ManyToMany set
    if request.user.profile.role == 'Technician':
        task = get_object_or_404(
            Task,
            id=task_id,
            assigned_technicians=request.user  # Django handles the 'in' logic automatically
        )
    else:
        # Admins/Supervisors can see everything
        task = get_object_or_404(Task, id=task_id)

    # Rest of your logic remains the same
    complaints = Complaint.objects.filter(task=task)
    subtasks = SubTask.objects.filter(task=task)
    task_items = task.items.all()
    attachments = task.attachments.all().order_by('-created_at')

    complaint_form = ComplaintForm()
    subtask_form = SubTaskForm()
    all_technicians = User.objects.filter(profile__role='Technician')


    context = {
        'task': task,
        'complaints': complaints,
        'subtasks': subtasks,
        'task_items': task_items,
        'attachments': attachments,
        'complaint_form': complaint_form,
        'subtask_form': subtask_form,
        'all_technicians': all_technicians,  # ADD THIS TO CONTEXT
    }

    return render(request, 'tasks/task_detail.html', context)


@login_required
def submit_complaint(request, task_id):
    # 1. UPDATED: Visibility restriction for Technicians
    # We check if the current user is in the assigned_technicians ManyToMany set
    if request.user.profile.role == 'Technician':
        task = get_object_or_404(
            Task,
            id=task_id,
            assigned_technicians=request.user  # Many-to-Many query
        )
    else:
        # Admins/Supervisors can access any task
        task = get_object_or_404(Task, id=task_id)

    if request.method == 'POST':
        form = ComplaintForm(request.POST, request.FILES)
        if form.is_valid():
            complaint = form.save(commit=False)
            complaint.task = task
            # Assuming your Complaint model has a technician field
            try:
                complaint.message = GoogleTranslator(source='auto', target='en').translate(complaint.message)
            except:
                pass
            complaint.technician = request.user
            complaint.save()
            if task.status == "Completed":
                send_task_to_google_sheet(task)
            messages.success(request, "Complaint submitted.")
            return redirect('task_detail', task_id=task.id)

    return redirect('task_detail', task_id=task.id)


@login_required
def add_subtask(request, task_id):
    # 1. UPDATED: Visibility restriction using ManyToMany field
    if request.user.profile.role == 'Technician':
        task = get_object_or_404(
            Task,
            id=task_id,
            assigned_technicians=request.user  # Many-to-Many lookup
        )
    else:
        task = get_object_or_404(Task, id=task_id)

    if request.method == 'POST':
        form = SubTaskForm(request.POST)
        if form.is_valid():
            subtask = form.save(commit=False)
            subtask.task = task
            subtask.save()

    return redirect('task_detail', task_id=task.id)


@login_required
def toggle_subtask(request, subtask_id):
    # 2. UPDATED: Fetching the SubTask itself, then checking its parent Task
    subtask = get_object_or_404(SubTask, id=subtask_id)
    task = subtask.task

    # Check permissions on the parent task
    if request.user.profile.role == 'Technician':
        if not task.assigned_technicians.filter(id=request.user.id).exists():
            messages.error(request, "Unauthorized")
            return redirect('task_list')

    subtask.completed = not subtask.completed
    subtask.save()

    return redirect('task_detail', task_id=task.id)


@login_required
def reports(request):
    context_stats = None
    # 1. Capture Filters
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    project_type = request.GET.get('project_type', '')
    selected_tech_id = request.GET.get('tech_id', '')
    selected_building = request.GET.get('building', '')
    selected_unit = request.GET.get('unit', '')

    # 1. Update unit queryset based on building
    all_buildings = Task.objects.values_list('building', flat=True).distinct().exclude(building__isnull=True)

    # Filter units only belonging to the selected building
    unit_queryset = Task.objects.values_list('unit', flat=True).distinct().exclude(unit__isnull=True)
    if selected_building:
        unit_queryset = unit_queryset.filter(building=selected_building)

    all_units = unit_queryset

    base_tasks = Task.objects.all()

    # Get staff list safely
    all_technicians = User.objects.filter(groups__name='Technician') | User.objects.filter(
        profile__role='Technician') | User.objects.filter(groups__name='Supervisor') | User.objects.filter(
        profile__role='Supervisor')
    if not all_technicians.exists():
        all_technicians = User.objects.annotate(t_count=Count('assigned_tasks')).filter(t_count__gt=0)

    # Apply standard page filters
    if date_from:
        base_tasks = base_tasks.filter(created_at__date__gte=date_from)
    if date_to:
        base_tasks = base_tasks.filter(created_at__date__lte=date_to)
    if project_type:
        base_tasks = base_tasks.filter(project_type=project_type)
    if selected_building: base_tasks = base_tasks.filter(building=selected_building)
    if selected_unit: base_tasks = base_tasks.filter(unit=selected_unit)

    # Fetch unique list for dropdowns
    all_buildings = Task.objects.values_list('building', flat=True).distinct().exclude(building__isnull=True)
    all_units = Task.objects.values_list('unit', flat=True).distinct().exclude(unit__isnull=True)

    # 2. Simple Status Counters
    total_tasks = base_tasks.count()
    completed = base_tasks.filter(status='Completed').count()
    active = base_tasks.filter(status__in=['In Progress', 'Active']).count()
    pending = base_tasks.filter(status__in=['Pending', 'Pending(قيد الانتظار)']).count()
    overdue = base_tasks.filter(status='Overdue').count()

    # 3. Cost Calculations (AED)
    def get_cost(work_type):
        res = base_tasks.filter(project_type=work_type).aggregate(total=Sum('budget'))
        try:
            return float(res['total']) if res['total'] else 0.0
        except:
            return 0.0

    cost_data = {
        'Paint': get_cost('Paint'), 'Electric': get_cost('Electric'),
        'Plumbing': get_cost('Plumbing'), 'Cleaning': get_cost('Cleaning'),
        'AC': get_cost('AC'), 'Carpenter': get_cost('Carpenter'),
        'Mason': get_cost('Mason') or get_cost('Mason(بناء)'),
        'Ceiling': get_cost('Ceiling') or get_cost('Ceiling(سقف)'),
        'Plumbing and Electric': get_cost('Plumbing and Electric') or get_cost('Plumbing and Electric'),

    }
    total_expenses = sum(cost_data.values())

    # 4. Monthly History Logs
    monthly_trends = (
        base_tasks.filter(completed_at__isnull=False)
        .annotate(month=TruncMonth('completed_at'))
        .values('month')
        .annotate(count=Count('id'))
        .order_by('month')
    )
    months_labels = [trend['month'].strftime('%b %Y') for trend in monthly_trends]
    months_data = [trend['count'] for trend in monthly_trends]

    techs_summary = User.objects.annotate(
        assigned_count=Count(
            Case(When(assigned_tasks__id__in=base_tasks.values('id'), then=1), output_field=IntegerField())
        ),
        completed_count=Count(
            Case(When(assigned_tasks__id__in=base_tasks.values('id'), assigned_tasks__status='Completed', then=1),
                 output_field=IntegerField())
        )
    ).filter(assigned_count__gt=0).order_by('-completed_count')

    tech_labels = [t.username for t in techs_summary]
    tech_assigned = [t.assigned_count for t in techs_summary]
    tech_completed = [t.completed_count for t in techs_summary]

    # 6. Simplified Individual Worker Overview
    tech_stats = None
    # 6. Simplified Individual Worker Overview
    if selected_tech_id:
        try:
            target_tech = User.objects.get(id=selected_tech_id)
            # UPDATED: Use the ManyToMany field lookup
            tech_jobs = base_tasks.filter(assigned_technicians=target_tech)

            # ... rest of your logic remains the same ...

            t_total = tech_jobs.count()
            t_completed = tech_jobs.filter(status='Completed').count()

            financials = tech_jobs.aggregate(total_cost=Sum('budget'), avg_cost=Avg('budget'))
            t_total_cost = financials['total_cost'] or 0.0
            t_avg_cost = financials['avg_cost'] or 0.0

            timed_jobs = tech_jobs.filter(status='Completed', completed_at__isnull=False, created_at__isnull=False)
            avg_hours_logged = 0.0
            if timed_jobs.exists():
                duration_query = timed_jobs.annotate(
                    duration=ExpressionWrapper(F('completed_at') - F('created_at'), output_field=DurationField())
                ).aggregate(avg_time=Avg('duration'))
                avg_time = duration_query['avg_time']

                if avg_time:
                    total_minutes = int(avg_time.total_seconds() // 60)

                    hours = total_minutes // 60
                    minutes = total_minutes % 60

                    if hours > 0 and minutes > 0:
                        avg_hours_logged = f"{hours} hour{'s' if hours != 1 else ''} {minutes} minute{'s' if minutes != 1 else ''}"
                    elif hours > 0:
                        avg_hours_logged = f"{hours} hour{'s' if hours != 1 else ''}"
                    else:
                        avg_hours_logged = f"{minutes} minute{'s' if minutes != 1 else ''}"

            tech_stats = {
                'username': target_tech.username,
                'total_tasks': t_total,
                'completed': t_completed,
                'total_cost': float(t_total_cost),
                'avg_cost': float(t_avg_cost),
                # 'avg_hours': round(avg_hours_logged, 1),
                'avg_hours': avg_hours_logged,
                'success_rate': round((t_completed / t_total * 100), 0) if t_total > 0 else 0
            }
        except User.DoesNotExist:
            pass

        if selected_tech_id or selected_building or selected_unit:
            filtered_stats = base_tasks
            t_total = filtered_stats.count()
            t_completed = filtered_stats.filter(status='Completed').count()
            financials = filtered_stats.aggregate(total_cost=Sum('budget'), avg_cost=Avg('budget'))

            # Calculate stats
            t_total = filtered_stats.count()
            t_completed = filtered_stats.filter(status='Completed').count()
            financials = filtered_stats.aggregate(total_cost=Sum('budget'), avg_cost=Avg('budget'))

            context_stats = {
                'label': selected_building or selected_unit or "Selected Technician",
                'total_tasks': t_total,
                'completed': t_completed,
                'total_cost': float(financials['total_cost'] or 0.0),
                'avg_cost': float(financials['avg_cost'] or 0.0),
                'success_rate': round((t_completed / t_total * 100), 0) if t_total > 0 else 0
            }

    context = {
        'total_tasks': total_tasks, 'completed': completed, 'active': active,
        'pending': pending, 'overdue': overdue, 'total_expenses': total_expenses,
        'all_technicians': all_technicians, 'selected_tech_id': selected_tech_id,
        'tech_stats': tech_stats,
        'cost_keys_json': json.dumps(list(cost_data.keys())),
        'cost_values_json': json.dumps(list(cost_data.values())),
        'months_labels_json': json.dumps(months_labels),
        'months_data_json': json.dumps(months_data),
        'tech_labels_json': json.dumps(tech_labels),
        'tech_assigned_json': json.dumps(tech_assigned),
        'tech_completed_json': json.dumps(tech_completed),
        'all_buildings': all_buildings,
        'all_units': all_units,
        'selected_building': selected_building,
        'selected_unit': selected_unit,
        'context_stats': context_stats,
    }
    return render(request, 'tasks/reports.html', context)


@api_view(['GET'])
def api_tasks(request):
    tasks = Task.objects.all()

    serializer = TaskSerializer(
        tasks,
        many=True
    )

    return Response(serializer.data)


from django.db.models import Q


def all_completed_tasks(request):
    user = request.user



    # 1. Gather Role Configuration Strings
    user_role = getattr(user, "role", None)
    if not user_role and hasattr(user, "profile"):
        user_role = getattr(user.profile, "role", None)

    # 2. Enforce Role Visibility Restrictions
    # PREFETCH is added here so the template can display assigned technicians correctly
    base_queryset = Task.objects.filter(status="Completed").prefetch_related("assigned_technicians")

    if (
            user.is_superuser
            or user.is_staff
            or user_role in ["Admin"]
            or user.groups.filter(name__in=["Admin"]).exists()
    ):
        base_tasks = base_queryset
    else:
        # FIXED: Use ManyToMany filter
        base_tasks = base_queryset.filter(assigned_technicians=user)

    # 3. Apply Filters from URL Query Parameters
    job_id = request.GET.get("job_id")
    user_query = request.GET.get("user")
    project_type = request.GET.get("project_type")
    date_from = request.GET.get("date_from")
    date_to = request.GET.get("date_to")
    building = request.GET.get("building")
    unit = request.GET.get("unit")

    if job_id and job_id.strip():
        base_tasks = base_tasks.filter(job_id__icontains=job_id.strip())

    # FIXED: Filter by technician username in ManyToMany
    if user_query and user_query.strip():
        base_tasks = base_tasks.filter(
            assigned_technicians__username__icontains=user_query.strip()
        ).distinct()

    if project_type and project_type.strip():
        base_tasks = base_tasks.filter(project_type=project_type)

    if date_from and date_from.strip():
        base_tasks = base_tasks.filter(completed_at__date__gte=date_from)

    if date_to and date_to.strip():
        try:
            parsed_date_to = datetime.strptime(date_to.strip(), "%Y-%m-%d").date()
            next_day = parsed_date_to + timedelta(days=1)
            base_tasks = base_tasks.filter(completed_at__lt=next_day)
        except ValueError:
            base_tasks = base_tasks.filter(completed_at__date__lte=date_to)

    if building and building.strip():
        base_tasks = base_tasks.filter(building__iexact=building.strip())

    if unit and unit.strip():
        base_tasks = base_tasks.filter(unit__iexact=unit.strip())

        # Automatically extract unique buildings and units from the database to populate the dropdowns
    buildings = Task.objects.exclude(building__isnull=True).exclude(building__exact='').values_list('building',
                                                                                                    flat=True).distinct()
    units = Task.objects.exclude(unit__isnull=True).exclude(unit__exact='').values('building', 'unit').distinct()


    return render(
        request,
        "tasks/all_tasks.html",
        {"tasks": base_tasks.distinct().order_by('-completed_at'), "title": "Completed Tasks (المهام المكتملة)","buildings": buildings,
           "units": units,},
    )


# 1. New Pending Tasks View
def all_pending_tasks(request):
    # Base query for tasks that are currently pending
    # Added distinct() because filtering by ManyToMany can return duplicates
    tasks = Task.objects.filter(
        Q(status__in=['Pending', 'Pending(قيد الانتظار)']) |
        (Q(status='Overdue') & Q(started_at__isnull=True))
    ).distinct()

    # Gather URL Query Parameters
    job_id = request.GET.get('job_id')
    user = request.GET.get('user')
    project_type = request.GET.get('project_type')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')

    # NEW: Capture building and unit
    building = request.GET.get('building')
    unit = request.GET.get('unit')

    if job_id and job_id.strip():
        tasks = tasks.filter(job_id__icontains=job_id.strip())

    if user and user.strip():
        tasks = tasks.filter(assigned_technicians__username__icontains=user.strip()).distinct()

    if project_type and project_type.strip():
        tasks = tasks.filter(project_type=project_type)

    if date_from and date_from.strip():
        tasks = tasks.filter(created_at__date__gte=date_from)

    if date_to and date_to.strip():
        try:
            parsed_date_to = datetime.strptime(date_to.strip(), "%Y-%m-%d").date()
            next_day = parsed_date_to + timedelta(days=1)
            tasks = tasks.filter(created_at__lt=next_day)
        except ValueError:
            tasks = tasks.filter(created_at__date__lte=date_to)

    # NEW: Apply Building and Unit filters
    if building and building.strip():
        tasks = tasks.filter(building__iexact=building.strip())

    if unit and unit.strip():
        tasks = tasks.filter(unit__iexact=unit.strip())

    # NEW: Get distinct options for the dropdowns
    buildings = Task.objects.exclude(building__isnull=True).exclude(building__exact='').values_list('building',
                                                                                                    flat=True).distinct()
    units = Task.objects.exclude(unit__isnull=True).exclude(unit__exact='').values('building', 'unit').distinct()

    return render(
        request,
        'tasks/all_tasks.html',
        {
            'tasks': tasks.order_by('-created_at'),
            'title': 'Pending Tasks',
            'buildings': buildings,
            'units': units,
        }
    )


def all_active_tasks(request):
    tasks = Task.objects.filter(
        Q(status__in=['In Progress', 'قيد التنفيذ']) |
        (Q(status='Overdue') & Q(started_at__isnull=False))
    ).distinct()

    job_id = request.GET.get('job_id')
    user = request.GET.get('user')
    project_type = request.GET.get('project_type')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')

    # NEW: Capture building and unit
    building = request.GET.get('building')
    unit = request.GET.get('unit')

    if job_id and job_id.strip():
        tasks = tasks.filter(job_id__icontains=job_id.strip())

    if user and user.strip():
        tasks = tasks.filter(assigned_technicians__username__icontains=user.strip()).distinct()

    if project_type and project_type.strip():
        tasks = tasks.filter(project_type=project_type)

    if date_from and date_from.strip():
        tasks = tasks.filter(started_at__date__gte=date_from)

    if date_to and date_to.strip():
        tasks = tasks.filter(started_at__date__lte=date_to)

    # NEW: Apply Building and Unit filters
    if building and building.strip():
        tasks = tasks.filter(building__iexact=building.strip())

    if unit and unit.strip():
        tasks = tasks.filter(unit__iexact=unit.strip())

    # NEW: Get distinct options for the dropdowns
    buildings = Task.objects.exclude(building__isnull=True).exclude(building__exact='').values_list('building',
                                                                                                    flat=True).distinct()
    units = Task.objects.exclude(unit__isnull=True).exclude(unit__exact='').values('building', 'unit').distinct()

    return render(
        request,
        'tasks/all_tasks.html',
        {
            'tasks': tasks.order_by('-started_at'),
            'title': 'Active Tasks',
            'buildings': buildings,
            'units': units,
        }
    )

def all_overdue_tasks(request):
    tasks = Task.objects.filter(status='Overdue').distinct()

    job_id = request.GET.get('job_id')
    user = request.GET.get('user')
    project_type = request.GET.get('project_type')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')

    if job_id and job_id.strip():
        tasks = tasks.filter(job_id__icontains=job_id.strip())

    # FIXED: Changed 'assigned_to' to 'assigned_technicians'
    if user and user.strip():
        tasks = tasks.filter(assigned_technicians__username__icontains=user.strip()).distinct()

    if project_type and project_type.strip():
        tasks = tasks.filter(project_type=project_type)

    if date_from and date_from.strip():
        tasks = tasks.filter(created_at__date__gte=date_from)

    if date_to and date_to.strip():
        tasks = tasks.filter(created_at__date__lte=date_to)

    return render(request, 'tasks/all_tasks.html', {'tasks': tasks, 'title': 'Overdue Tasks'})


def check_and_update_overdue_tasks(queryset):
    """
    Scans a queryset of tasks and bulk-updates records that have passed
    their deadlines but are not yet marked as 'Completed' or 'Overdue'.
    """
    now = timezone.now()
    expired_tasks = queryset.filter(
        deadline__lt=now
    ).exclude(
        status__in=['Completed', 'Overdue']
    )

    if expired_tasks.exists():
        expired_tasks.update(status='Overdue', is_overdue=True)


@login_required
def add_task_item_detail(request, task_id):
    if request.method == 'POST':
        task = get_object_or_404(Task, id=task_id)
        sub_cat = request.POST.get('sub_category')
        qty = request.POST.get('quantity')

        if sub_cat and sub_cat.strip():
            TaskItem.objects.create(
                task=task,
                sub_category=sub_cat.strip(),
                quantity=qty.strip() if qty else "-"
            )
            messages.success(request, "New item appended to breakdown successfully!")

    return redirect('task_detail', task_id=task_id)


@login_required
def upload_task_attachment(request, task_id):
    # 1. Base query: get the task
    task = get_object_or_404(Task, id=task_id)

    # 2. Authorization check: If technician, ensure they are in the assigned_technicians list
    if request.user.profile.role == 'Technician':
        if not task.assigned_technicians.filter(id=request.user.id).exists():
            messages.error(request, "You are not authorized to upload to this task.")
            return redirect('task_detail', task_id=task.id)

    if request.method == 'POST':
        uploaded_image = request.FILES.get('task_image')
        uploaded_video = request.FILES.get('task_video')

        # Guard clause: Check if absolutely nothing was sent
        if not uploaded_image and not uploaded_video:
            messages.error(request, "No image or video file was received by the server.")
            return redirect('task_detail', task_id=task.id)

        # File format validation arrays
        allowed_image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp']
        allowed_video_extensions = ['.mp4', '.webm', '.mov', '.avi']

        is_valid = True
        save_image = None
        save_video = None

        # Validate Image if provided
        if uploaded_image:
            img_ext = os.path.splitext(uploaded_image.name)[1].lower()
            if img_ext in allowed_image_extensions:
                save_image = uploaded_image
            else:
                messages.error(request, f"Unsupported image format: {img_ext}")
                is_valid = False

        # Validate Video if provided
        if uploaded_video:
            vid_ext = os.path.splitext(uploaded_video.name)[1].lower()
            if vid_ext in allowed_video_extensions:
                save_video = uploaded_video
            else:
                messages.error(request, f"Unsupported video format: {vid_ext}")
                is_valid = False

        # Database Commit Execution
        if is_valid and (save_image or save_video):
            TaskAttachment.objects.create(
                task=task,
                uploaded_by=request.user,
                image=save_image,
                video=save_video
            )
            messages.success(request, "Verification media uploaded successfully!")

    return redirect('task_detail', task_id=task.id)


@login_required
def delete_task_attachment(request, attachment_id):
    # Fetch attachment checking authorization constraints
    attachment = get_object_or_404(TaskAttachment, id=attachment_id)
    task_id = attachment.task.id

    # Restrict deletion capability rules: Only Admin or the specific User who uploaded it
    if request.user.is_superuser or request.user.profile.role == 'Admin' or attachment.uploaded_by == request.user:
        # Delete file from local media storage disk safely
        if attachment.image and os.path.exists(attachment.image.path):
            os.remove(attachment.image.path)

        attachment.delete()
        messages.success(request, "Image deleted successfully! (تم حذف الصورة بنجاح)")
    else:
        messages.error(request, "Unauthorized action. You cannot delete this picture.")

    return redirect('task_detail', task_id=task_id)


logger = logging.getLogger(__name__)


def update_budget_ajax(request, task_id):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=400)

    try:
        data = json.loads(request.body)
        new_budget = data.get('budget', '').strip()

        task = get_object_or_404(Task, id=task_id)
        task.budget = new_budget
        task.save()

        if task.status == "Completed":
            send_task_to_google_sheet(task)

        return JsonResponse({'status': 'success', 'message': 'Budget updated successfully'})
    except Exception as e:
        logger.error(f"Error updating budget for task {task_id}: {str(e)}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


def get_sub_categories_ajax(request):
    raw_project_type = request.GET.get('project_type', '').strip()
    project_type = raw_project_type.split('(')[0].strip()

    # Fetch directly from the database only
    items = list(MaintenanceWorkItem.objects.filter(project_type=project_type)
                 .values_list('name_english', flat=True))

    return JsonResponse({'items': sorted(items)})


@csrf_exempt
def add_sub_category_ajax(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        # No need to split/parse, just take the value directly from the select box
        p_type = data.get('project_type')
        eng = data.get('name_english')
        arb = data.get('name_arabic')

        item, created = MaintenanceWorkItem.objects.get_or_create(
            project_type=p_type,
            name_english=eng,
            name_arabic=arb
        )
        if created:
            return JsonResponse({'success': True})
        return JsonResponse({'success': False, 'error': 'Already exists'})
    return JsonResponse({'success': False}, status=400)


class CustomLoginView(LoginView):
    template_name = 'registration/login.html'
    redirect_authenticated_user = True

    def get_redirect_url(self):
        # This ensures it uses your LOGIN_REDIRECT_URL setting
        return super().get_redirect_url()


# In your views.py or your AJAX endpoint for completing a task
def complete_overdue_task(request, task_id):
    task = get_object_or_404(Task, id=task_id)

    # Calculate the delay before marking it completed
    if task.deadline and task.status == 'Overdue':
        task.final_delay_duration = timezone.now() - task.deadline

    task.status = 'Completed'
    task.completed_at = timezone.now()
    task.save()
    # This automatically pushes any admin corrections straight to the spreadsheet.
    if task.status == "Completed":
        send_task_to_google_sheet(task)
    return JsonResponse({'status': 'success'})


@login_required
def add_maintenance_item(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        # Assuming you have a model named MaintenanceWorkItem
        MaintenanceWorkItem.objects.create(
            project_type=data.get('project_type'),
            name_english=data.get('name_en'),
            name_arabic=data.get('name_ar')
        )
        return JsonResponse({'success': True})
    return JsonResponse({'success': False, 'message': 'Invalid request'})


def update_description_ajax(request, task_id):
    if request.method != "POST":
        return JsonResponse(
            {
                "status": "error",
                "message": "Invalid request"
            },
            status=400
        )

    try:
        data = json.loads(request.body)
        description = data.get("description", "").strip()
        task = get_object_or_404(Task, id=task_id)

        # --- TRANSLATION INTEGRATION ---
        if description:
            try:
                translator = GoogleTranslator(source='auto', target='en')
                task.description = translator.translate(description)
            except Exception as e:
                # Fallback to the original text if the translation API experiences an outage
                print(f"Translation failed: {e}")
                task.description = description
        else:
            task.description = description

        task.save()
        if task.status == "Completed":
            send_task_to_google_sheet(task)

        # Return the saved description text so the frontend can display the newly translated string
        return JsonResponse(
            {
                "status": "success",
                "description": task.description
            }
        )

    except Exception as e:
        return JsonResponse(
            {
                "status": "error",
                "message": str(e)
            },
            status=500
        )


@require_POST
def delete_task_item_ajax(request, item_id):
    item = get_object_or_404(TaskItem, id=item_id)
    task = item.task

    # Replace 'TaskItem' with your actual model name for the sub-items
    item = get_object_or_404(TaskItem, id=item_id)
    item.delete()

    if task.status == "Completed":
        send_task_to_google_sheet(task)

    return JsonResponse({'status': 'success', 'message': 'Item deleted successfully.'})


def add_task_item_detail(request, task_id):
    task = get_object_or_404(Task, id=task_id)

    if request.method == 'POST':
        # Grab raw form values
        sub = request.POST.get('sub_category', '').strip()
        qty = request.POST.get('quantity', '').strip()

        translator = GoogleTranslator(source='auto', target='en')

        # --- 1. Translate Sub-Category ---
        if sub:
            try:
                translated_sub = translator.translate(sub)
            except Exception:
                translated_sub = sub  # Fallback to original if API drops out
        else:
            translated_sub = "General"

        # --- 2. Translate Quantity / Details ---
        if qty:
            if qty.isdigit():
                translated_qty = qty  # Skip translator entirely for pure numbers
            else:
                try:
                    translated_qty = translator.translate(qty)
                except Exception:
                    translated_qty = qty  # Fallback
        else:
            translated_qty = "0"

        # --- 3. Save to Database ---
        TaskItem.objects.create(
            task=task,
            sub_category=translated_sub,
            quantity=translated_qty
        )

        messages.success(request, "Missed maintenance item added successfully in English!")

        # Check if the updated task is currently marked completed.
        # This automatically pushes any admin corrections straight to the spreadsheet.
        if task.status == "Completed":
            send_task_to_google_sheet(task)

    return redirect('task_detail', task_id=task.id)  # Change to your actual detail view name


def update_start_date_ajax(request, task_id):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=400)

    try:
        data = json.loads(request.body)
        date_str = data.get('started_at', '').strip()
        task = get_object_or_404(Task, id=task_id)

        if date_str:
            # datetime-local format is YYYY-MM-DDTHH:MM, parse to aware timezone
            task.started_at = timezone.make_aware(timezone.datetime.fromisoformat(date_str))
        else:
            task.started_at = None

        task.save()
        if task.status == "Completed":
            send_task_to_google_sheet(task)
        return JsonResponse({'status': 'success', 'message': 'Start date updated successfully'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


def update_completed_date_ajax(request, task_id):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=400)

    try:
        data = json.loads(request.body)
        date_str = data.get('completed_at', '').strip()
        task = get_object_or_404(Task, id=task_id)

        if date_str:
            task.completed_at = timezone.make_aware(timezone.datetime.fromisoformat(date_str))
        else:
            task.completed_at = None

        task.save()
        if task.status == "Completed":
            send_task_to_google_sheet(task)
        return JsonResponse({'status': 'success', 'message': 'End date updated successfully'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


load_dotenv()


@csrf_exempt
def process_audio_file(request):
    if request.method == 'POST' and request.FILES.get('audio'):
        audio_file = request.FILES['audio']

        # Initialize Groq client
        client = Groq(api_key=os.getenv("GROQ_API_KEY"))

        try:
            # ---------------------------------------------------------
            # STEP 1: Transcribe the Audio
            # Whisper-large-v3 automatically detects the language!
            # ---------------------------------------------------------
            transcription = client.audio.transcriptions.create(

                file=("audio.webm", audio_file.read()),

                model="whisper-large-v3",

                prompt="Maintenance, plumbing, electric, carpentry, Al Raihan Plaza, Al Naser Plaza, G01, unit, technician, repair, install, faucet, socket, fused."

            )
            transcript_text = transcription.text
            print(f"Heard: {transcript_text}")  # For your debugging

            # ---------------------------------------------------------
            # STEP 2: Parse, Translate, and Format with Llama 3
            # ---------------------------------------------------------
            prompt = f"""
                        You are an expert maintenance dispatcher in the UAE.
                        Analyze the following voice transcript and extract the information into a strict JSON format.

                        CRITICAL MAPPING RULES - YOU MUST CHOOSE FROM THESE LISTS:
                        - ALLOWED BUILDINGS: "Aliya Villa", "Al Farah Plaza", "Al Huda Building", "Al Ithihad Building", "Al Khaleej Building", "Al Maktab Building", "Al Maass Building", "Al Naser Plaza", "Al Raihan Plaza", "Al Salam Building", "Arbab House (YBN)", "Bader Building", "Fatma YBN Villa", "Farm Helio", "Mohammed Yousef Nasser Villa", "Muhammed Yousuf Building", "Rashidiya Building", "Sanahiya Building", "Souk Building", "Villa Sanahiya", "Other"
                        - ALLOWED PROJECT TYPES: "Paint", "Electric", "Plumbing", "Cleaning", "Carpenter", "AC", "Mason", "Ceiling"
                        - "CRITICAL CORRECTIONS": If the transcript mentions 'shutter' in the context of a bathroom, toilet, or plumbing, ALWAYS map it to 'Shattaf'.

                        JSON Keys & Rules:
                        1. "description": A clear English summary of the task.
                        2. "building": MUST be exactly one of the ALLOWED BUILDINGS. Intelligently map misspellings (e.g., "al mas bldg" MUST output "Al Maass Building").
                        3. "unit": The unit number. Extract the unit number specifically as a string of digits. If the transcript contains phonetic Bengali for numbers (like 'one-zero-four'), convert these to digits ('104'). If no unit is mentioned in the transcript, MUST output exactly "None".
                        4. "technicians": A strict JSON list of individual first names ONLY. Example: ["Mumtaz", "Subair"]. Return [] if none mentioned.
                        5. "project_type": MUST be exactly one of the ALLOWED PROJECT TYPES. (e.g., "ac repairing" MUST output "AC", "electric work" MUST output "Electric").
                        6. "sub_category": List the specific work performed. If a problem was reported (like "light fused") and a solution was applied (like "LED installed"), include both components in the list to ensure full documentation.


                        Transcript: "{transcript_text}"
                        """

            completion = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system",
                     "content": "You are an API that outputs ONLY valid JSON. No markdown, no conversational text."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,  # Keep it low for consistent, factual outputs
                response_format={"type": "json_object"}  # Forces Llama to return perfect JSON
            )

            # Convert string response to actual Python dictionary
            json_response = json.loads(completion.choices[0].message.content)
            print(f"Parsed Data: {json_response}")  # For your debugging

            # Send the data back to your frontend!
            return JsonResponse(json_response)

        except Exception as e:
            print(f"Groq API Error: {e}")
            return JsonResponse({'error': 'Failed to process audio with AI.'}, status=500)

    return JsonResponse({'error': 'No file uploaded'}, status=400)


def update_technicians_ajax(request, task_id):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=400)

    try:
        task = get_object_or_404(Task, id=task_id)
        # Using getlist because there are multiple inputs with name="technicians"
        tech_ids = request.POST.getlist('technicians')

        if tech_ids:
            task.assigned_technicians.set(tech_ids) # Updates the ManyToMany field
            task.save()
            return JsonResponse({'status': 'success', 'message': 'Technicians updated successfully'})
        else:
            return JsonResponse({'status': 'error', 'message': 'Please select at least one technician'}, status=400)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


from django.http import JsonResponse
from django.shortcuts import get_object_or_404


def update_location_ajax(request, task_id):
    if request.method == 'POST':
        task = get_object_or_404(Task, id=task_id)

        building = request.POST.get('building')
        unit = request.POST.get('unit')

        if building and unit:
            task.building = building
            task.unit = unit

            # Reconstruct title format exactly like create_task view logic
            project_type_str = str(getattr(task, 'project_type', 'General')).strip()
            loc_parts = [str(building), str(unit)]
            location = "-".join([p for p in loc_parts if p]) or "No Location"

            # Check if any technicians are assigned to set title metadata
            if not task.assigned_technicians.exists():
                task.title = f"{location}-{project_type_str} - [UNASSIGNED]"[:200]
            else:
                task.title = f"{location}-{project_type_str}"[:200]

            task.save()

            # Safely build a comma-separated list of technicians for the title banner
            tech_list = ", ".join([t.username for t in task.assigned_technicians.all()])

            return JsonResponse({
                'status': 'success',
                'message': 'Location and Title updated successfully!',
                'new_title': task.title,
                'tech_list': tech_list
            })
        else:
            return JsonResponse({'status': 'error', 'message': 'Building and Unit are required.'}, status=400)





@login_required
def bulk_print_invoices(request):
    # Security: Only Superusers or Admins can access this
    is_admin = request.user.is_superuser or (hasattr(request.user, 'profile') and request.user.profile.role == 'Admin')
    if not is_admin:
        raise PermissionDenied("Only administrators can bulk print invoices.")

    # Get the data the JavaScript sent us via the URL link
    task_ids_str = request.GET.get('ids', '')
    customer_name = request.GET.get('name', 'EDRAK Properties')
    customer_address = request.GET.get('address', 'Rashidiya 2, Ajman, UAE')

    # Convert the comma-separated string of IDs into a list of numbers
    task_ids = [int(i) for i in task_ids_str.split(',') if i.isdigit()]

    # Fetch ONLY the tasks that match the IDs and are strictly 'Completed'
    tasks = Task.objects.filter(id__in=task_ids, status='Completed').order_by('-completed_at')
    context = {
        'tasks': tasks,
        'customer_name': customer_name,
        'customer_address': customer_address,
        'today': timezone.now().strftime('%d-%m-%Y'),
    }

    # We haven't made this file yet, but we will in Step 3!
    return render(request, 'tasks/bulk_invoice_print.html', context)


@login_required
def ai_audit_dashboard(request):
    # Only show completed tasks for auditing
    completed_tasks = Task.objects.filter(status__icontains='Completed').order_by('-completed_at')[:50]
    return render(request, 'tasks/ai_audit.html', {'tasks': completed_tasks})


# 2. The AI Calculation Logic
def calculate_ai_charge_ajax(request, task_id):
    task = get_object_or_404(Task, id=task_id)

    # 1. READ AND FILTER THE CSV BY CATEGORY (pricing_chart.csv)
    csv_path = os.path.join(settings.BASE_DIR, 'data', 'pricing_chart.csv')
    relevant_rules = []

    try:
        with open(csv_path, mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                csv_project_type = str(row.get('Project Type', '')).strip().lower()
                task_project_type = str(task.project_type).strip().lower()

                if csv_project_type == task_project_type:
                    task_name = row.get('TASK LIST', 'Unknown Task').strip()
                    charge = row.get('CHARGE AED', '0').strip()
                    duration = row.get('DURATION', 'N/A').strip()
                    relevant_rules.append(f"- {task_name} | Cost: {charge} | Time: {duration}")

    except FileNotFoundError:
        return JsonResponse({'status': 'error', 'message': 'pricing_chart.csv not found in the data folder.'})

    pricing_summary = "\n".join(relevant_rules)
    if not pricing_summary:
        pricing_summary = "No standard pricing rules found. Use logical standard rates."

    # 2. FETCH LIVE DATA FROM GOOGLE SHEETS SAFELY
    sheet_export_url = "https://docs.google.com/spreadsheets/d/1JHDA_x8JF0oRRyImg50P1n0G31va4tSY4VOauRri-Qc/export?format=csv&gid=0"
    live_sheet_context = "No live recent data retrieved."

    try:
        response = requests.get(sheet_export_url, timeout=5)
        if response.status_code == 200:
            # Prevent HTML login pages from destroying the AI's context window
            if "<!DOCTYPE html>" in response.text or "<html" in response.text.lower():
                live_sheet_context = "[SYSTEM WARNING: Google Sheet is private. Change sharing to 'Anyone with the link can view'.]"
            else:
                lines = response.text.split('\n')
                recent_lines = [lines[0]] + lines[-15:] if len(lines) > 15 else lines
                live_sheet_context = "\n".join(recent_lines)
    except requests.exceptions.RequestException as e:
        print(f"Failed to fetch Google Sheet: {e}")

    # 3. ENHANCED AI PROMPT
        # 3. ENHANCED AI PROMPT
        # 3. ENHANCED AI PROMPT
    system_prompt = f"""You are a strict, logical AI Cost Estimator for property maintenance in the UAE.
        Category: '{task.project_type}'.

        OFFICIAL PRICING RULES:
        {pricing_summary}

        RECENT LIVE CONTEXT (For terminology/standards):
        {live_sheet_context}

        CRITICAL RULES:
        1. COMPREHENSIVE ANALYSIS (USE ALL DATA): You MUST evaluate ALL provided data before forming a conclusion. First, parse the Technician Notes and 'Items'. Then, cross-reference this information against BOTH the Official Pricing Rules AND the Recent Live Context. Do not stop at the first partial match. Form your final cost only after verifying all sources.
        2. ITEM PARSING LOGIC: When evaluating the 'Items' list:
           - If a sub-category is listed as 'General', completely ignore it and rely on the Technician Notes instead.
           - If a quantity is listed as '0', you MUST treat it as exactly 1 unit or 1 piece.
        3. INDEPENDENCE: Do NOT use the technician's Inputted Charge to influence your selection. Calculate the cost strictly based on the rules and context.
        4. NO INVENTED MATH OR METRICS: NEVER invent hourly rates, measurements (like 'meters'), or timeframes. Only apply exact flat rates from the pricing rules based on the parsed items and notes. NEVER make up your own multipliers.
        5. NO HEAVY HARDWARE HALLUCINATIONS: NEVER match a vague symptom to expensive parts (e.g., 'compressor', 'pump') unless explicitly stated as repaired or replaced in the Items or Notes.
        6. NO SQUISHED NUMBERS: You must output an ARRAY OF INDIVIDUAL INTEGERS representing each charge. Never combine them into one number (e.g., output [35, 50], never [3550]).

        Return the result EXACTLY in this JSON format:
        {{
            "individual_costs": [50],
            "justification": "Analyzed ALL data. Items listed 'General (0)'. Treated quantity '0' as 1 unit. Notes stated 'replaced switch'. Cross-referenced Official Pricing Rules which lists electrical switch replacement at 50 AED. Verified Recent Live Context which confirmed standard switch jobs are 50 AED. Applied standard 50 AED flat rate."
        }}
        """

    short_desc = str(task.description)[:300] if task.description else "No description"
    task_items = ", ".join([f"{item.sub_category} ({item.quantity})" for item in task.items.all()])
    technician_count = task.assigned_technicians.count() or 1
    actual_budget = float(task.budget) if task.budget else 0.0

    user_prompt = f"""
    - Type: {task.project_type}
    - Technician Notes: {short_desc}
    - Items: {task_items}
    - Time: {task.time_taken}
    - Inputted Charge: {actual_budget} AED
    """

    # 4. EXECUTE VIA GROQ
    try:
        client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        completion = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.0,  # Dropped to 0 for maximum deterministic math
            max_tokens=400,
            response_format={"type": "json_object"}
        )

        response_json = json.loads(completion.choices[0].message.content)
        raw_matched_costs = response_json.get('individual_costs', [])

        # 5. AGGRESSIVE NUMBER PARSING (To catch Llama 3 hallucinations like '3550')
        clean_costs = []
        if isinstance(raw_matched_costs, list):
            for cost in raw_matched_costs:
                cost_str = str(cost).strip()
                if cost_str.isdigit():
                    clean_costs.append(int(cost_str))
        elif isinstance(raw_matched_costs, (int, str)):
            # If AI returns "3550", we fallback to 0 to trigger manual review rather than charging 3550
            cost_str = str(raw_matched_costs).strip()
            if cost_str.isdigit() and len(cost_str) > 3:
                clean_costs = [0]
            elif cost_str.isdigit():
                clean_costs = [int(cost_str)]

        if not clean_costs:
            clean_costs = [0]

        raw_charge = sum(clean_costs)
        ai_predicted_charge = round(raw_charge / 5) * 5

        # 6. THRESHOLD COMPARISON
        difference = abs(ai_predicted_charge - actual_budget)

        if actual_budget > 0 and difference <= 10:
            final_charge = actual_budget
            threshold_note = f"\n\n[System Note: AI predicted {ai_predicted_charge} AED based on items {clean_costs}. Inputted charge ({actual_budget} AED) is within the ±10 AED variance. Accepted inputted charge.]"
        else:
            final_charge = ai_predicted_charge
            threshold_note = f"\n\n[System Note: AI identified costs {clean_costs} totaling {raw_charge} AED. The inputted charge of {actual_budget} AED differed by {difference} AED. Standard pricing enforced.]"

        justification = response_json.get('justification', '') + threshold_note

        return JsonResponse({
            'status': 'success',
            'ai_charge': final_charge,
            'ai_points': int(final_charge),
            'justification': justification
        })

    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


from django.db.models import Sum, Count, Avg, F
from django.utils.decorators import method_decorator
import json


def is_admin_strict(user):
    return user.is_superuser or (hasattr(user, 'profile') and user.profile.role == 'Admin')


@login_required
def all_overtime_tasks(request):
    if not is_admin_strict(request.user):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied("Only administrators can access the Overtime System.")

    # --- THE FILTER FIX ---
    # Now looks for our new flag OR legacy tasks with >0 hours
    tasks = Task.objects.filter(
        Q(is_overtime=True) | Q(overtime_hours__gt=0) | Q(overtime_charge__gt=0)
    ).prefetch_related(
        'assigned_technicians', 'items', 'complaint_set'
    ).distinct().order_by('-created_at')

    # Capture Parameters
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    job_id = request.GET.get('job_id')
    user_query = request.GET.get('user')
    project_type = request.GET.get('project_type')
    building = request.GET.get('building')
    unit = request.GET.get('unit')

    # Apply String Filters
    if job_id and job_id.strip():
        tasks = tasks.filter(job_id__icontains=job_id.strip())
    if user_query and user_query.strip():
        tasks = tasks.filter(assigned_technicians__username__icontains=user_query.strip())
    if project_type and project_type.strip():
        tasks = tasks.filter(project_type=project_type)
    if building and building.strip():
        tasks = tasks.filter(building__iexact=building.strip())
    if unit and unit.strip():
        tasks = tasks.filter(unit__iexact=unit.strip())

    # Date Filters
    if date_from and date_from.strip():
        tasks = tasks.filter(created_at__gte=date_from.strip())

    if date_to and date_to.strip():
        try:
            parsed_to = datetime.strptime(date_to.strip(), "%Y-%m-%d")
            next_day = parsed_to + timedelta(days=1)
            tasks = tasks.filter(created_at__lt=next_day)
        except ValueError:
            pass

    # Fetch Dropdowns
    buildings = Task.objects.exclude(building__isnull=True).exclude(building__exact='').values_list('building', flat=True).distinct()
    units = Task.objects.exclude(unit__isnull=True).exclude(unit__exact='').values_list('unit', flat=True).distinct()

    context = {
        'tasks': tasks,
        'title': 'Overtime Tasks (مهام العمل الإضافي)',
        'buildings': buildings,
        'units': units,
    }
    return render(request, 'tasks/overtime_tasks.html', context)

@login_required
def overtime_reports(request):
    if not request.user.is_superuser:  # Adjust permissions as needed
        return render(request, '403.html')

    # 1. Base Query: Only get tasks that have actual overtime logged
    tasks = Task.objects.filter(overtime_hours__gt=0)

    # 2. Capture Filters
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    building = request.GET.get('building')
    unit = request.GET.get('unit')
    tech_id = request.GET.get('tech_id')

    # 3. Apply Filters
    if date_from:
        tasks = tasks.filter(created_at__date__gte=date_from)
    if date_to:
        tasks = tasks.filter(created_at__date__lte=date_to)
    if building:
        tasks = tasks.filter(building__iexact=building)
    if unit:
        tasks = tasks.filter(unit__iexact=unit)
    if tech_id:
        tasks = tasks.filter(assigned_technicians__id=tech_id)

    # 4. Calculate Top-Level KPIs
    kpis = tasks.aggregate(
        total_hours=Sum('overtime_hours'),
        total_cost=Sum('overtime_charge'),
        total_tasks=Count('id', distinct=True)
    )

    # 5. Chart Data: Overtime by Technician
    tech_stats = tasks.values('assigned_technicians__username').annotate(
        total_hrs=Sum('overtime_hours'),
        total_cst=Sum('overtime_charge')
    ).exclude(assigned_technicians__username__isnull=True)

    tech_labels = [t['assigned_technicians__username'] for t in tech_stats]
    tech_hours = [float(t['total_hrs'] or 0) for t in tech_stats]
    tech_costs = [float(t['total_cst'] or 0) for t in tech_stats]

    # 6. Chart Data: Overtime by Building
    building_stats = tasks.values('building').annotate(
        total_cst=Sum('overtime_charge')
    ).exclude(Q(building__isnull=True) | Q(building=''))

    bldg_labels = [b['building'] for b in building_stats]
    bldg_costs = [float(b['total_cst'] or 0) for b in building_stats]

    # 7. Get distinct values for the filter dropdowns
    all_buildings = Task.objects.exclude(Q(building__isnull=True) | Q(building='')).values_list('building',
                                                                                                flat=True).distinct()
    all_units = Task.objects.exclude(Q(unit__isnull=True) | Q(unit='')).values_list('unit', flat=True).distinct()
    all_technicians = User.objects.filter(is_active=True)  # Or however you define technicians

    context = {
        # KPIs
        'total_hours': kpis['total_hours'] or 0,
        'total_cost': kpis['total_cost'] or 0,
        'total_tasks': kpis['total_tasks'] or 0,

        # JSON for Charts
        'tech_labels_json': json.dumps(tech_labels),
        'tech_hours_json': json.dumps(tech_hours),
        'tech_costs_json': json.dumps(tech_costs),
        'bldg_labels_json': json.dumps(bldg_labels),
        'bldg_costs_json': json.dumps(bldg_costs),

        # Dropdown lists
        'all_buildings': all_buildings,
        'all_units': all_units,
        'all_technicians': all_technicians,

        # Keep selected filters in context to maintain state
        'selected_building': building,
        'selected_unit': unit,
        'selected_tech_id': tech_id,

        # Send raw tasks for the detailed table at the bottom
        'detailed_tasks': tasks.order_by('-created_at')[:100]  # Limit to 100 for performance
    }
    return render(request, 'tasks/overtime_reports.html', context)


@csrf_exempt
@login_required
def update_overtime_ajax(request, task_id):
    if request.method == 'POST' and is_admin_strict(request.user):
        try:
            data = json.loads(request.body)
            task = get_object_or_404(Task, id=task_id)

            hours_input = str(data.get('hours') or '').strip()
            charge_input = str(data.get('charge') or '').strip()

            # --- TRANSLATE HH.MM EXACTLY (No Hacks Needed) ---
            if not hours_input or hours_input in ['0', '0.0', '0.00']:
                decimal_hours = 0.0
            else:
                try:
                    if '.' in hours_input:
                        h_part, m_part = hours_input.split('.', 1)
                        if len(m_part) == 1:
                            m_part += '0'

                        h = int(h_part) if h_part else 0
                        m = int(m_part[:2])

                        decimal_hours = h + (m / 60.0)
                    else:
                        decimal_hours = float(hours_input)
                except ValueError:
                    decimal_hours = 0.0

            final_charge = float(charge_input) if charge_input else 0.0

            # Store the accurate math AND flip the permanent boolean flag
            task.overtime_hours = decimal_hours
            task.overtime_charge = final_charge
            task.is_overtime = True  # <--- THIS KEEPS IT ON THE BOARD
            task.save()

            # Safely calculate response values
            try:
                tot_chg = task.total_service_charge
            except AttributeError:
                tot_chg = float(task.budget or 0) + task.overtime_charge

            try:
                tot_time = task.total_work_time
            except AttributeError:
                tot_time = str(task.time_taken)

            return JsonResponse({
                'status': 'success',
                'total_service_charge': tot_chg,
                'total_work_time': tot_time
            })
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

    return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)

@login_required
def get_assignable_overtime_tasks_ajax(request):
    if not is_admin_strict(request.user):
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    # Get all tasks (so admin can assign OT to anything)
    tasks = Task.objects.all().order_by('-created_at')[:100]

    task_data = []
    for t in tasks:
        task_data.append({
            'id': t.id,
            'job_id': t.job_id,
            'title': t.title,
            'status': t.status,
            'current_ot_hours': float(t.overtime_hours or 0),
            'current_ot_charge': float(t.overtime_charge or 0),
            'assigned_to': t.assigned_to_display or 'Unassigned'
        })
    return JsonResponse({'tasks': task_data})


@login_required
@require_POST
def update_status_ajax(request, task_id):

    task = get_object_or_404(Task, id=task_id)

    if request.user.profile.role != "Admin":
        return JsonResponse(
            {"status":"error"},
            status=403
        )

    status = request.POST.get("status")

    valid_statuses = [choice[0] for choice in Task.STATUS_CHOICES]

    if status not in valid_statuses:

        return JsonResponse({

            "status":"error",

            "message":"Invalid status"

        },status=400)

    task.status = status

    if status == "Completed":

        if not task.completed_at:
            task.completed_at = timezone.now()

    elif status == "In Progress":

        if not task.started_at:
            task.started_at = timezone.now()

    task.save()

    return JsonResponse({

        "status":"success"

    })


@login_required
@require_POST
def delete_task_ajax(request, task_id):

    task = get_object_or_404(Task,id=task_id)

    if request.user.profile.role != "Admin":

        return JsonResponse({

            "status":"error"

        },status=403)

    task.delete()

    return JsonResponse({

        "status":"success"

    })


@login_required
def overtime_technicians(request):
    if not request.user.is_superuser and getattr(request.user.profile, 'role', '') != 'Admin':
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied("Only administrators can manage personnel overtime.")

    # Fetch all relevant staff
    technicians = User.objects.filter(
        profile__role__in=['Technician', 'Supervisor']
    ).prefetch_related('assigned_tasks', 'profile')

    tech_data = []
    for tech in technicians:
        # Get all tasks for this technician that actually have overtime
        ot_tasks = tech.assigned_tasks.filter(overtime_hours__gt=0)

        # Calculate their share of the Task OT
        # (Assuming the OT is split evenly among assigned technicians on that specific task)
        task_accrued_hrs = 0.0
        task_accrued_chg = 0.0

        for t in ot_tasks:
            tech_count = t.assigned_technicians.count()
            if tech_count > 0:
                task_accrued_hrs += float(t.overtime_hours or 0) / tech_count
                task_accrued_chg += float(t.overtime_charge or 0) / tech_count

        manual_hrs = float(tech.profile.manual_ot_hours or 0)
        manual_chg = float(tech.profile.manual_ot_charge or 0)

        tech_data.append({
            'id': tech.id,
            'username': tech.username,
            'role': tech.profile.role,
            'task_ot_hrs': task_accrued_hrs,
            'task_ot_chg': task_accrued_chg,
            'manual_ot_hrs': manual_hrs,
            'manual_ot_charge': manual_chg,
            'total_hrs': task_accrued_hrs + manual_hrs,
            'total_chg': task_accrued_chg + manual_chg,
            'has_details': ot_tasks.exists()
        })

    return render(request, 'tasks/overtime_technicians.html', {'technicians': tech_data})


@login_required
@require_POST
def update_tech_overtime_ajax(request, tech_id):
    if not request.user.is_superuser and getattr(request.user.profile, 'role', '') != 'Admin':
        return JsonResponse({'status': 'error'}, status=403)

    try:
        data = json.loads(request.body)
        target_user = get_object_or_404(User, id=tech_id)

        target_user.profile.manual_ot_hours = float(data.get('hours') or 0.00)
        target_user.profile.manual_ot_charge = float(data.get('charge') or 0.00)
        target_user.profile.save()

        return JsonResponse({'status': 'success'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@login_required
def get_tech_overtime_details_ajax(request, tech_id):
    if not request.user.is_superuser and getattr(request.user.profile, 'role', '') != 'Admin':
        return JsonResponse({'status': 'error'}, status=403)

    target_user = get_object_or_404(User, id=tech_id)
    ot_tasks = target_user.assigned_tasks.filter(overtime_hours__gt=0).order_by('-completed_at')

    task_list = []
    for t in ot_tasks:
        tech_count = t.assigned_technicians.count()
        # Calculate their specific slice of the job's overtime
        split_hrs = float(t.overtime_hours or 0) / tech_count if tech_count else 0
        split_chg = float(t.overtime_charge or 0) / tech_count if tech_count else 0

        task_list.append({
            'job_id': t.job_id,
            'title': t.title,
            'date': t.completed_at.strftime('%Y-%m-%d') if t.completed_at else 'Active',
            'split_hrs': round(split_hrs, 2),
            'split_chg': round(split_chg, 2),
            'shared_with': tech_count - 1  # How many other guys were on this job
        })

    return JsonResponse({'tasks': task_list, 'username': target_user.username})



@login_required
def save_material_request_ajax(request, task_id):
    if request.method == 'POST':
        task = get_object_or_404(Task, id=task_id)
        data = json.loads(request.body)
        items = data.get('items', [])
        action = data.get('action', 'save')

        mat_req, created = MaterialRequest.objects.get_or_create(task=task)
        if created or mat_req.status != 'Approved':
            mat_req.submitted_by = request.user

        # Clear old rows and recreate them
        mat_req.items.all().delete()
        for item in items:
            name = item.get('name', '').strip()
            qty = item.get('qty', '').strip()
            if name or qty:
                RequestedMaterialItem.objects.create(request=mat_req, material_name=name, quantity=qty)

        # ADMIN APPROVAL LOGIC
        is_admin = getattr(request.user.profile, 'role', '') == 'Admin' or request.user.is_superuser

        if action == 'approve' and is_admin:
            mat_req.status = 'Approved'
            mat_req.approved_at = timezone.now()

            # Clear previously approved materials from TaskItem to prevent duplicates if admin edits it again
            TaskItem.objects.filter(task=task, sub_category__startswith='[Material]').delete()

            # Append materials to the official sub-items breakdown!
            for item in items:
                name = item.get('name', '').strip()
                qty = item.get('qty', '').strip()
                if name:
                    TaskItem.objects.create(task=task, sub_category=f"[Material] {name}", quantity=qty or "1")
        else:
            mat_req.status = 'Pending'

        mat_req.save()
        return JsonResponse({'status': 'success', 'req_status': mat_req.status})
    return JsonResponse({'status': 'error'}, status=400)


@login_required
def get_material_request_ajax(request, task_id):
    task = get_object_or_404(Task, id=task_id)

    # Safe check that prevents the 500 error crash
    if hasattr(task, 'material_request'):
        mat_req = task.material_request
        items = [{'name': i.material_name, 'qty': i.quantity} for i in mat_req.items.all()]
        return JsonResponse({'status': 'success', 'items': items, 'req_status': mat_req.status})

    return JsonResponse({'status': 'success', 'items': [], 'req_status': 'None'})


@login_required
def disapprove_material_request_ajax(request, task_id):
    is_admin = getattr(request.user.profile, 'role', '') == 'Admin' or request.user.is_superuser
    if not is_admin:
        return JsonResponse({'status': 'error'}, status=403)

    task = get_object_or_404(Task, id=task_id)
    if hasattr(task, 'material_request'):
        task.material_request.status = 'Pending'
        task.material_request.approved_at = None
        task.material_request.save()
        # Immediately strip them from the sub-item breakdown
        TaskItem.objects.filter(task=task, sub_category__startswith='[Material]').delete()

    return JsonResponse({'status': 'success'})


@login_required
def material_approvals_view(request):
    if getattr(request.user.profile, 'role', '') != 'Admin' and not request.user.is_superuser:
        return redirect('dashboard')

    requests_qs = MaterialRequest.objects.all().order_by('-updated_at')

    # --- NEW: Fetch General Material Requests ---
    general_requests = GeneralMaterialRequest.objects.all().order_by('-created_at')
    general_pending_count = GeneralMaterialRequest.objects.filter(status='Pending').count()

    # (Keep your existing filter logic for task material requests here)

    return render(request, 'tasks/material_approvals.html', {
        'requests': requests_qs,
        'general_requests': general_requests,
        'general_pending_count': general_pending_count,
        'buildings': Task.objects.exclude(building__isnull=True).exclude(building__exact='').values_list('building',
                                                                                                         flat=True).distinct(),
        'units': Task.objects.exclude(unit__isnull=True).exclude(unit__exact='').values('building', 'unit').distinct()
    })


@login_required
def approved_materials_list(request):
    user = request.user
    user_role = getattr(user.profile, 'role', '') if hasattr(user, 'profile') else ''
    is_admin = user.is_superuser or user_role == 'Admin'

    # 1. Base Querysets Filtered by User Role
    if is_admin:
        approved_reqs = MaterialRequest.objects.filter(status='Approved')
        approved_gen_reqs = GeneralMaterialRequest.objects.filter(status='Approved')
    elif user.username == 'approval_admin' or user_role == 'approval_admin':
        # Restrict approval admin (e.g., filter specific supplier if model has supplier field)
        approved_reqs = MaterialRequest.objects.filter(status='Approved')
        approved_gen_reqs = GeneralMaterialRequest.objects.filter(status='Approved')
    else:
        # Technicians only view materials for their assigned tasks or personal submissions
        approved_reqs = MaterialRequest.objects.filter(
            status='Approved',
            task__assigned_technicians=user
        ).distinct()
        approved_gen_reqs = GeneralMaterialRequest.objects.filter(
            status='Approved',
            submitted_by=user
        )

    # 2. Tag and Combine both Querysets into a Single Timeline
    for req in approved_reqs:
        req.is_general = False
    for req in approved_gen_reqs:
        req.is_general = True

    combined_requests = sorted(
        chain(approved_reqs, approved_gen_reqs),
        key=lambda instance: instance.approved_at or timezone.now(),
        reverse=True
    )

    return render(request, 'tasks/approved_materials.html', {
        'combined_requests': combined_requests,
        'buildings': Task.objects.exclude(building__isnull=True).exclude(building__exact='').values_list('building', flat=True).distinct(),
        'units': Task.objects.exclude(unit__isnull=True).exclude(unit__exact='').values('building', 'unit').distinct()
    })


@login_required
def print_material_approval(request, req_id):
    mat_req = get_object_or_404(MaterialRequest, id=req_id, status='Approved')

    # Security check: Ensure a technician cannot type in a random ID to print another team's voucher
    is_admin = getattr(request.user.profile, 'role', '') == 'Admin' or request.user.is_superuser
    if not is_admin and not mat_req.task.assigned_technicians.filter(id=request.user.id).exists():
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied("You do not have access to view this approval document.")

    return render(request, 'tasks/print_material_approval.html', {'req': mat_req})


@login_required
def bulk_print_overtime(request):
    # Security: Only Superusers or Admins can access this
    is_admin = request.user.is_superuser or (hasattr(request.user, 'profile') and request.user.profile.role == 'Admin')
    if not is_admin:
        raise PermissionDenied("Only administrators can print overtime reports.")

    # Get the comma-separated IDs from the URL
    task_ids_str = request.GET.get('ids', '')

    # Safely convert to a list of integers
    task_ids = [int(i) for i in task_ids_str.split(',') if i.isdigit()]

    # Fetch tasks matching the selected IDs
    tasks = Task.objects.filter(id__in=task_ids).order_by('-completed_at')

    # Calculate the total overtime hours safely
    total_ot_hours = sum(task.overtime_hours for task in tasks if task.overtime_hours)

    context = {
        'tasks': tasks,
        'total_ot_hours': total_ot_hours,
        'today': timezone.now().strftime('%d/%m/%Y'),
    }

    return render(request, 'tasks/bulk_overtime_print.html', context)




from .models import GeneralMaterialRequest, GeneralRequestedMaterialItem


@login_required
def create_general_material_request_ajax(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            items = data.get('items', [])

            if not items:
                return JsonResponse({'status': 'error', 'message': 'Please add at least one material.'}, status=400)

            gen_req = GeneralMaterialRequest.objects.create(
                submitted_by=request.user,
                status='Pending'
            )

            for item in items:
                name = item.get('name', '').strip()
                qty = item.get('qty', '').strip()
                if name:
                    GeneralRequestedMaterialItem.objects.create(
                        request=gen_req,
                        material_name=name,
                        quantity=qty or "1"
                    )

            return JsonResponse({'status': 'success', 'message': 'General Material Request submitted successfully!'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

    return JsonResponse({'status': 'error', 'message': 'Invalid request'}, status=400)


@login_required
def approve_general_material_request_ajax(request, req_id):
    is_admin = getattr(request.user.profile, 'role', '') == 'Admin' or request.user.is_superuser
    if not is_admin:
        return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)

    gen_req = get_object_or_404(GeneralMaterialRequest, id=req_id)
    gen_req.status = 'Approved'
    gen_req.approved_at = timezone.now()
    gen_req.save()

    return JsonResponse({'status': 'success', 'message': 'General material request approved.'})


@login_required
def reject_general_material_request_ajax(request, req_id):
    is_admin = getattr(request.user.profile, 'role', '') == 'Admin' or request.user.is_superuser
    if not is_admin:
        return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)

    gen_req = get_object_or_404(GeneralMaterialRequest, id=req_id)
    gen_req.status = 'Rejected'
    gen_req.save()

    return JsonResponse({'status': 'success', 'message': 'General material request rejected.'})


@login_required
def print_general_material_approval(request, req_id):
    gen_req = get_object_or_404(GeneralMaterialRequest, id=req_id, status='Approved')

    is_admin = getattr(request.user.profile, 'role', '') == 'Admin' or request.user.is_superuser
    if not is_admin and gen_req.submitted_by != request.user:
        raise PermissionDenied("You do not have access to view this approval document.")

    return render(request, 'tasks/print_general_material_approval.html', {'req': gen_req})


@login_required
def bulk_print_material_approvals(request):
    is_admin = request.user.is_superuser or (hasattr(request.user, 'profile') and request.user.profile.role == 'Admin')
    if not is_admin:
        raise PermissionDenied("Only administrators can bulk print material approvals.")

    req_ids_str = request.GET.get('ids', '')
    req_ids = [int(i) for i in req_ids_str.split(',') if i.isdigit()]

    requests_qs = MaterialRequest.objects.filter(id__in=req_ids, status='Approved')
    general_requests_qs = GeneralMaterialRequest.objects.filter(id__in=req_ids, status='Approved')

    context = {
        'requests': requests_qs,
        'general_requests': general_requests_qs,
        'today': timezone.now().strftime('%d-%m-%Y'),
    }
    return render(request, 'tasks/bulk_material_approval_print.html', context)


@login_required
@require_POST
def delete_material_request_ajax(request, req_id, req_type):
    # Security: Ensure only admins can delete records
    is_admin = getattr(request.user.profile, 'role', '') == 'Admin' or request.user.is_superuser
    if not is_admin:
        return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)

    try:
        if req_type == 'task':
            req_obj = get_object_or_404(MaterialRequest, id=req_id)
            req_obj.delete()
        elif req_type == 'general':
            req_obj = get_object_or_404(GeneralMaterialRequest, id=req_id)
            req_obj.delete()
        else:
            return JsonResponse({'status': 'error', 'message': 'Invalid request type'}, status=400)

        return JsonResponse({'status': 'success'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)




@login_required
def create_general_material_request_with_name_ajax(request):
    # Admin-only security check
    is_admin = getattr(request.user.profile, 'role', '') == 'Admin' or request.user.is_superuser
    if not is_admin:
        return JsonResponse({'status': 'error', 'message': 'Unauthorized. Admins only.'}, status=403)

    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            items = data.get('items', [])
            custom_name = data.get('custom_name', '').strip()

            if not items:
                return JsonResponse({'status': 'error', 'message': 'Please add at least one material.'}, status=400)

            if not custom_name:
                return JsonResponse({'status': 'error', 'message': 'Please enter a name for the order.'}, status=400)

            # Create the general material request with the custom override name
            gen_req = GeneralMaterialRequest.objects.create(
                submitted_by=request.user,
                custom_name=custom_name,
                status='Pending'
            )

            for item in items:
                name = item.get('name', '').strip()
                qty = item.get('qty', '').strip()
                if name:
                    GeneralRequestedMaterialItem.objects.create(
                        request=gen_req,
                        material_name=name,
                        quantity=qty or "1"
                    )

            return JsonResponse({'status': 'success', 'message': 'General Material Request submitted successfully!'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

    return JsonResponse({'status': 'error', 'message': 'Invalid request'}, status=400)