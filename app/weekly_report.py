"""Weekly reports share the profile's local event definitions and UTC windows."""
def generate_weekly_report(project_id, service):
    from .profile_insights import context, weekly
    return weekly(context(service, project_id))
