from django.urls import path

from .views import (
    AiChatCompletionsView,
    AiModelsListView,
    PersonalAIDocumentDetailView,
    PersonalAIDocumentShareToProjectView,
    PersonalAIDocumentsView,
    PersonalAIPreferenceView,
    PersonalNoteDetailView,
    PersonalNotesView,
    PersonalPromptDetailView,
    PersonalPromptsView,
    AiRunCreateView,
    AiRunDetailView,
    AiRunExecuteView,
    AiRunLogsView,
)

urlpatterns = [
    path("ai/runs", AiRunCreateView.as_view(), name="ai-runs-create"),
    path("ai/runs/<int:pk>", AiRunDetailView.as_view(), name="ai-runs-detail"),
    path("ai/runs/<int:pk>/execute", AiRunExecuteView.as_view(), name="ai-runs-execute"),
    path("ai/runs/<int:pk>/logs", AiRunLogsView.as_view(), name="ai-runs-logs"),
    path("ai/chat/completions", AiChatCompletionsView.as_view(), name="ai-chat-completions"),
    path("ai/models", AiModelsListView.as_view(), name="ai-models-list"),
    path("ai/personal/preferences", PersonalAIPreferenceView.as_view(), name="ai-personal-preferences"),
    path("ai/personal/documents", PersonalAIDocumentsView.as_view(), name="ai-personal-documents"),
    path("ai/personal/documents/<int:pk>", PersonalAIDocumentDetailView.as_view(), name="ai-personal-document-detail"),
    path(
        "ai/personal/documents/<int:pk>/share-to-project",
        PersonalAIDocumentShareToProjectView.as_view(),
        name="ai-personal-document-share-to-project",
    ),
    path("ai/personal/prompts", PersonalPromptsView.as_view(), name="ai-personal-prompts"),
    path("ai/personal/prompts/<int:pk>", PersonalPromptDetailView.as_view(), name="ai-personal-prompt-detail"),
    path("ai/personal/notes", PersonalNotesView.as_view(), name="ai-personal-notes"),
    path("ai/personal/notes/<int:pk>", PersonalNoteDetailView.as_view(), name="ai-personal-note-detail"),
]
