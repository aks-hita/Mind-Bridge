"""
views.py — Django views that call sql_engine.py exclusively.
No ORM. Every database interaction goes through the SQL engine.
"""
from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import JsonResponse
from .sql_engine import (
    init_db,
    sp_register_student, sp_login, sp_book_appointment,
    sp_cancel_appointment, sp_complete_session, sp_submit_feedback,
    sp_mark_notifications_read,
    view_student_dashboard, view_counsellor_dashboard,
    view_recommendations_for_student, view_all_counsellors,
    view_appointment_detail, view_diagnosis_categories,
)

# ── Auth helpers ──────────────────────────────────────────────────────────────

def _student(request):
    return request.session.get('role') == 'student'

def _counsellor(request):
    return request.session.get('role') == 'counsellor'

def _require_student(view_fn):
    def wrapper(request, *a, **kw):
        if not _student(request):
            return redirect('login')
        return view_fn(request, *a, **kw)
    wrapper.__name__ = view_fn.__name__
    return wrapper

def _require_counsellor(view_fn):
    def wrapper(request, *a, **kw):
        if not _counsellor(request):
            return redirect('login')
        return view_fn(request, *a, **kw)
    wrapper.__name__ = view_fn.__name__
    return wrapper

# ── Public views ──────────────────────────────────────────────────────────────

def home(request):
    counsellors = view_all_counsellors()
    return render(request, 'home.html', {'counsellors': counsellors})

def login_view(request):
    if request.method == 'POST':
        email    = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')
        role     = request.POST.get('role', 'student')
        ok, result = sp_login(email, password, role)
        if ok:
            request.session['user_id']   = result['id']
            request.session['user_name'] = result['full_name']
            request.session['role']      = role
            request.session['email']     = email
            return redirect('student_dashboard' if role == 'student' else 'counsellor_dashboard')
        messages.error(request, result)
    return render(request, 'login.html')

def register_view(request):
    if request.method == 'POST':
        ok, result = sp_register_student(
            full_name    = request.POST.get('full_name','').strip(),
            email        = request.POST.get('email','').strip(),
            password     = request.POST.get('password',''),
            phone        = request.POST.get('phone',''),
            gender       = request.POST.get('gender',''),
            dob          = request.POST.get('dob',''),
            department   = request.POST.get('department',''),
            year_of_study= request.POST.get('year_of_study') or None,
        )
        if ok:
            request.session['user_id']   = result
            request.session['user_name'] = request.POST.get('full_name','')
            request.session['role']      = 'student'
            request.session['email']     = request.POST.get('email','')
            messages.success(request, 'Welcome to MindBridge! 🌿')
            return redirect('student_dashboard')
        messages.error(request, result)
    return render(request, 'register.html')

def logout_view(request):
    request.session.flush()
    return redirect('home')

def counsellors_page(request):
    return render(request, 'counsellors.html', {'counsellors': view_all_counsellors()})

# ── Student views ─────────────────────────────────────────────────────────────

@_require_student
def student_dashboard(request):
    sid  = request.session['user_id']
    data = view_student_dashboard(sid)
    sp_mark_notifications_read('student', sid)
    return render(request, 'student_dashboard.html', {**data, 'user_name': request.session['user_name']})

@_require_student
def recommendations_view(request):
    sid  = request.session['user_id']
    data = view_recommendations_for_student(sid)
    return render(request, 'recommendations.html', {**data, 'user_name': request.session['user_name']})

@_require_student
def book_appointment(request):
    if request.method == 'POST':
        ok, result = sp_book_appointment(
            student_id    = request.session['user_id'],
            counsellor_id = int(request.POST.get('counsellor_id')),
            apt_date      = request.POST.get('apt_date'),
            apt_time      = request.POST.get('apt_time'),
            mode          = request.POST.get('mode', 'online'),
            reason        = request.POST.get('reason', ''),
        )
        if ok:
            messages.success(request, '✅ Appointment booked successfully!')
            return redirect('student_dashboard')
        messages.error(request, result)
    return render(request, 'book_appointment.html', {
        'counsellors': view_all_counsellors(),
        'user_name': request.session['user_name'],
    })

@_require_student
def cancel_appointment_student(request, apt_id):
    ok, msg = sp_cancel_appointment(apt_id, request.session['user_id'], 'student')
    if ok: messages.success(request, msg)
    else:  messages.error(request, msg)
    return redirect('student_dashboard')

@_require_student
def session_detail_student(request, apt_id):
    apt = view_appointment_detail(apt_id)
    if not apt or apt['student_id'] != request.session['user_id']:
        return redirect('student_dashboard')
    if request.method == 'POST':
        ok, msg = sp_submit_feedback(
            apt_id, request.session['user_id'],
            request.POST.get('feedback',''),
            request.POST.get('rating', 3),
        )
        if ok: messages.success(request, msg)
        else:  messages.error(request, msg)
        return redirect('session_detail_student', apt_id=apt_id)
    return render(request, 'session_detail.html', {'apt': apt, 'user_name': request.session['user_name']})

# ── Counsellor views ──────────────────────────────────────────────────────────

@_require_counsellor
def counsellor_dashboard(request):
    cid  = request.session['user_id']
    data = view_counsellor_dashboard(cid)
    sp_mark_notifications_read('counsellor', cid)
    return render(request, 'counsellor_dashboard.html', {**data, 'user_name': request.session['user_name']})

@_require_counsellor
def complete_session_view(request, apt_id):
    cid = request.session['user_id']
    apt = view_appointment_detail(apt_id)
    if not apt or apt['counsellor_id'] != cid:
        return redirect('counsellor_dashboard')
    if request.method == 'POST':
        ok, msg = sp_complete_session(
            appointment_id      = apt_id,
            notes               = request.POST.get('notes',''),
            duration            = int(request.POST.get('duration', 60)),
            diagnosis_category_id= request.POST.get('diagnosis_category') or None,
            severity            = request.POST.get('severity',''),
            follow_up_needed    = request.POST.get('follow_up_needed') == '1',
            counsellor_id       = cid,
        )
        if ok: messages.success(request, msg)
        else:  messages.error(request, msg)
        return redirect('counsellor_dashboard')
    categories = view_diagnosis_categories()
    return render(request, 'complete_session.html', {
        'apt': apt, 'categories': categories,
        'user_name': request.session['user_name'],
    })

@_require_counsellor
def cancel_appointment_counsellor(request, apt_id):
    ok, msg = sp_cancel_appointment(apt_id, request.session['user_id'], 'counsellor')
    if ok: messages.success(request, msg)
    else:  messages.error(request, msg)
    return redirect('counsellor_dashboard')

@_require_counsellor
def session_detail_counsellor(request, apt_id):
    cid = request.session['user_id']
    apt = view_appointment_detail(apt_id)
    if not apt or apt['counsellor_id'] != cid:
        return redirect('counsellor_dashboard')
    return render(request, 'session_detail.html', {'apt': apt, 'user_name': request.session['user_name']})
