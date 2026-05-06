from django.urls import path
from core import views

urlpatterns = [
    path('',                                              views.home,                         name='home'),
    path('login/',                                        views.login_view,                   name='login'),
    path('register/',                                     views.register_view,                name='register'),
    path('logout/',                                       views.logout_view,                  name='logout'),
    path('counsellors/',                                  views.counsellors_page,             name='counsellors'),
    path('dashboard/',                                    views.student_dashboard,            name='student_dashboard'),
    path('recommendations/',                              views.recommendations_view,         name='recommendations'),
    path('book/',                                         views.book_appointment,             name='book_appointment'),
    path('appointment/<int:apt_id>/cancel/',              views.cancel_appointment_student,   name='cancel_apt_student'),
    path('appointment/<int:apt_id>/',                     views.session_detail_student,       name='session_detail_student'),
    path('counsellor/dashboard/',                         views.counsellor_dashboard,         name='counsellor_dashboard'),
    path('counsellor/appointment/<int:apt_id>/complete/', views.complete_session_view,        name='complete_session'),
    path('counsellor/appointment/<int:apt_id>/cancel/',   views.cancel_appointment_counsellor,name='cancel_apt_counsellor'),
    path('counsellor/appointment/<int:apt_id>/',          views.session_detail_counsellor,    name='session_detail_counsellor'),
]
