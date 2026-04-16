from rest_framework import serializers


class TaskSerializer(serializers.Serializer):
    id = serializers.CharField()
    title = serializers.CharField()
    column = serializers.CharField()
    priority = serializers.CharField()
    due = serializers.CharField()

    class Meta:
        ref_name = "WorkspaceTask"


class EmployeeSerializer(serializers.Serializer):
    id = serializers.CharField()
    full_name = serializers.CharField()
    role = serializers.CharField()
    avatar = serializers.CharField()
    status = serializers.CharField()
    email = serializers.CharField()
    telegram = serializers.CharField()
    timezone = serializers.CharField()
    hours = serializers.CharField()
    x = serializers.IntegerField()
    y = serializers.IntegerField()
    points = serializers.IntegerField()
    next_goal = serializers.IntegerField()
    next_goal_label = serializers.CharField()
    tasks = TaskSerializer(many=True)


class ZoneSerializer(serializers.Serializer):
    x = serializers.IntegerField()
    y = serializers.IntegerField()
    w = serializers.IntegerField()
    h = serializers.IntegerField()
    label = serializers.CharField()
    color = serializers.CharField()
    stroke_color = serializers.CharField()


class DepartmentSerializer(serializers.Serializer):
    id = serializers.CharField()
    floor = serializers.IntegerField()
    name = serializers.CharField()
    status = serializers.CharField()
    employee_count = serializers.IntegerField()
    online_count = serializers.IntegerField()
    risky_tasks = serializers.IntegerField()
    overdue_tasks = serializers.IntegerField()
    lead = serializers.CharField()


class BuildingListItemSerializer(serializers.Serializer):
    id = serializers.CharField()
    name = serializers.CharField()
    status = serializers.CharField()
    floors = serializers.IntegerField()
    employees = serializers.IntegerField()
    online_now = serializers.IntegerField()
    risky_tasks = serializers.IntegerField()
    overdue_tasks = serializers.IntegerField()
    color = serializers.CharField()
    height_ratio = serializers.FloatField()
    latest_event = serializers.CharField()
    logo = serializers.CharField()


class BuildingDetailSerializer(serializers.Serializer):
    id = serializers.CharField()
    name = serializers.CharField()
    departments = DepartmentSerializer(many=True)


class WorkspaceSerializer(serializers.Serializer):
    building_name = serializers.CharField()
    department = serializers.CharField()
    zones = ZoneSerializer(many=True)
    employees = EmployeeSerializer(many=True)


class DocumentSerializer(serializers.Serializer):
    id = serializers.CharField()
    title = serializers.CharField()
    type = serializers.CharField()
    updated_at = serializers.CharField()
    owner = serializers.CharField()


class ActivitySerializer(serializers.Serializer):
    id = serializers.CharField()
    type = serializers.CharField()
    title = serializers.CharField()
    timestamp = serializers.CharField()


class ProjectSerializer(serializers.Serializer):
    id = serializers.CharField()
    name = serializers.CharField()
    status = serializers.CharField()
    summary = serializers.CharField()

    class Meta:
        ref_name = "WorkspaceProject"


class CommentSerializer(serializers.Serializer):
    id = serializers.CharField()
    author = serializers.CharField()
    text = serializers.CharField()
    created_at = serializers.CharField()


class PerformanceSerializer(serializers.Serializer):
    completed_tasks = serializers.IntegerField()
    total_tasks = serializers.IntegerField()
    on_time_rate = serializers.IntegerField()
    response_rate = serializers.IntegerField()


class EmployeeWorkspaceContextSerializer(serializers.Serializer):
    employee = EmployeeSerializer()
    my_tasks = TaskSerializer(many=True)
    documents = DocumentSerializer(many=True)
    activity_feed = ActivitySerializer(many=True)
    project_context = ProjectSerializer(many=True)


class EmployeeProfileSerializer(serializers.Serializer):
    employee = EmployeeSerializer()
    building_name = serializers.CharField()
    department = serializers.CharField()
    projects = ProjectSerializer(many=True)
    activity_feed = ActivitySerializer(many=True)
    comments_history = CommentSerializer(many=True)
    performance = PerformanceSerializer()
