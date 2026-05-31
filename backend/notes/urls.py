from django.urls import path

from .views import (
    TagListView,
    NoteDeleteView,
    NoteDetailView,
    NoteEditView,
    NoteMarkdownPreviewView,
    NoteListView,
    NoteUploadView,
    NoteVersionListView,
    NoteVersionRestoreView,
    TrashNoteDestroyView,
    TrashNoteListView,
    TrashNoteRestoreView,
)

urlpatterns = [
    path('tags/', TagListView.as_view(), name='tag-list'),
    path('', NoteListView.as_view(), name='note-list'),
    path('upload/', NoteUploadView.as_view(), name='note-upload'),
    path('preview/', NoteMarkdownPreviewView.as_view(), name='note-preview'),
    path('trash/', TrashNoteListView.as_view(), name='trash-note-list'),
    path('<int:pk>/', NoteDetailView.as_view(), name='note-detail'),
    path('<int:pk>/edit/', NoteEditView.as_view(), name='note-edit'),
    path('<int:pk>/versions/', NoteVersionListView.as_view(), name='note-version-list'),
    path('<int:pk>/versions/<int:version_pk>/restore/', NoteVersionRestoreView.as_view(), name='note-version-restore'),
    path('<int:pk>/delete/', NoteDeleteView.as_view(), name='note-delete'),
    path('trash/<int:pk>/restore/', TrashNoteRestoreView.as_view(), name='trash-note-restore'),
    path('trash/<int:pk>/destroy/', TrashNoteDestroyView.as_view(), name='trash-note-destroy'),
]
