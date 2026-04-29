from django.urls import path
from . import views

app_name = 'assignments'

urlpatterns = [
    # Dashboard
    path('', views.assignment_dashboard, name='dashboard'),
    
    # Assignment Management
    path('assignments/', views.AssignmentListView.as_view(), name='assignment_list'),
    path('assignments/create/', views.AssignmentCreateView.as_view(), name='assignment_create'),
    path('assignments/<int:pk>/', views.AssignmentDetailView.as_view(), name='assignment_detail'),
    path('assignments/<int:pk>/update/', views.AssignmentUpdateView.as_view(), name='assignment_update'),
    path('assignments/<int:pk>/publish/', views.publish_assignment, name='publish_assignment'),
    path('assignments/<int:assignment_id>/assign/<int:tasker_id>/', views.assign_to_tasker, name='assign_to_tasker'),
    
    # File Management
    path('assignments/<int:assignment_id>/upload-file/', views.upload_assignment_file, name='upload_file'),
    
    # Tasker Management
    path('tasker/profile/', views.tasker_profile_view, name='tasker_profile'),
    path('taskers/', views.TaskerListView.as_view(), name='tasker_list'),
    
    # Submissions
    path('assignments/<int:assignment_id>/submit/', views.submit_assignment, name='submit_assignment'),
    path('submissions/<int:submission_id>/review/', views.review_submission, name='review_submission'),
]
