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


class FlexibleObjectSerializer(serializers.Serializer):
    class Meta:
        ref_name = "WorkspaceFlexibleObject"


class EmployeeHeaderSerializer(serializers.Serializer):
    id = serializers.CharField()
    full_name = serializers.CharField()
    role = serializers.CharField()
    title = serializers.CharField()
    avatar = serializers.CharField()
    department = serializers.CharField()
    status = serializers.CharField()
    role_source_of_truth = serializers.CharField(required=False)


class ContractMetaSerializer(serializers.Serializer):
    encoding = serializers.CharField()
    locale = serializers.CharField()
    timestamp_format = serializers.CharField()
    header_role_source_of_truth = serializers.CharField()


class EmployeeCabinetSummarySerializer(serializers.Serializer):
    id = serializers.CharField()
    full_name = serializers.CharField()
    role = serializers.CharField()
    title = serializers.CharField()
    avatar = serializers.CharField()
    status = serializers.CharField()
    email = serializers.CharField()
    telegram = serializers.CharField()
    timezone = serializers.CharField()
    hours = serializers.CharField()


class WorkspaceEmployeeCabinetSerializer(serializers.Serializer):
    employee = EmployeeCabinetSummarySerializer()
    greeting = serializers.JSONField()
    today_focus = serializers.JSONField()
    quick_actions = serializers.JSONField()
    stats = serializers.JSONField()
    tasks_grouped = serializers.JSONField()
    project_context = serializers.JSONField()
    activity_feed = serializers.JSONField()
    ai_context = serializers.JSONField()
    role_extras = serializers.JSONField(required=False)
    viewer_role = serializers.CharField()
    contract_meta = ContractMetaSerializer(required=False)


class EmployeeOwnerProfileSerializer(serializers.Serializer):
    view = serializers.CharField()
    header = EmployeeHeaderSerializer()
    contacts = serializers.JSONField()
    performance = serializers.JSONField()
    projects = serializers.JSONField()
    achievements = serializers.JSONField()
    bonus_goals = serializers.JSONField()
    activity_feed = serializers.JSONField()
    comments_history = serializers.JSONField()
    preferences = serializers.JSONField()
    editable_fields = serializers.JSONField()


class EmployeePublicProfileSerializer(serializers.Serializer):
    view = serializers.CharField()
    header = EmployeeHeaderSerializer()
    contacts = serializers.JSONField()
    public_projects = serializers.JSONField()
    public_achievements = serializers.JSONField()
    public_stats = serializers.JSONField()


class UpdateMyEmployeeProfileSerializer(serializers.Serializer):
    personal_email = serializers.EmailField(required=False)
    phone = serializers.CharField(required=False)
    telegram = serializers.CharField(required=False)
    city = serializers.CharField(required=False)
    working_hours = serializers.CharField(required=False)
    timezone = serializers.CharField(required=False)
    preferences = serializers.DictField(required=False)


class QuickTaskCreateSerializer(serializers.Serializer):
    title = serializers.CharField()
    slot = serializers.ChoiceField(choices=["today", "this_week", "later"])
    priority = serializers.ChoiceField(choices=["high", "medium", "low"], required=False)
    project_id = serializers.CharField(required=False)


class QuickTaskCreateResponseSerializer(serializers.Serializer):
    task_id = serializers.CharField()
    slot = serializers.CharField()
    title = serializers.CharField()


class WorkspaceTaskAliasCreateSerializer(serializers.Serializer):
    title = serializers.CharField()
    column = serializers.ChoiceField(choices=["todo", "in_progress", "done"], required=False)
    status = serializers.ChoiceField(choices=["todo", "in_progress", "done"], required=False)
    priority = serializers.ChoiceField(choices=["high", "medium", "low"], required=False)
    due = serializers.CharField(required=False)
    project_id = serializers.CharField(required=False)


class WorkspaceTaskAliasPatchSerializer(serializers.Serializer):
    title = serializers.CharField(required=False)
    column = serializers.ChoiceField(choices=["todo", "in_progress", "done"], required=False)
    status = serializers.ChoiceField(choices=["todo", "in_progress", "done"], required=False)
    priority = serializers.ChoiceField(choices=["high", "medium", "low"], required=False)
    due = serializers.CharField(required=False, allow_null=True)
