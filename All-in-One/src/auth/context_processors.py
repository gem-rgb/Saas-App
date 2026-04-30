from auth.permissions import get_role_context, social_provider_enabled


def role_context(request):
    context = get_role_context(request.user)
    google_enabled = social_provider_enabled("google")
    github_enabled = social_provider_enabled("github")
    context.update(
        {
            "google_social_login_enabled": google_enabled,
            "github_social_login_enabled": github_enabled,
            "social_login_enabled": google_enabled or github_enabled,
        }
    )
    return context
