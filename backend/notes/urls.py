from django.urls import path

from .views import (
    NoteDeleteView,
    NoteListView,
    NoteUploadView,
    TrashNoteDestroyView,
    TrashNoteListView,
    TrashNoteRestoreView,
)

urlpatterns = [
    path('', NoteListView.as_view(), name='note-list'),
    path('upload/', NoteUploadView.as_view(), name='note-upload'),
    path('trash/', TrashNoteListView.as_view(), name='trash-note-list'),
    path('<int:pk>/delete/', NoteDeleteView.as_view(), name='note-delete'),
    path('trash/<int:pk>/restore/', TrashNoteRestoreView.as_view(), name='trash-note-restore'),
    path('trash/<int:pk>/destroy/', TrashNoteDestroyView.as_view(), name='trash-note-destroy'),
]
