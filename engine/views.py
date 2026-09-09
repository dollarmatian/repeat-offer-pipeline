import json
from datetime import datetime

from django.http import JsonResponse
from django.utils.dateparse import parse_datetime
from django.views import View

from engine import metrics, presenters, resolution
from engine.models import DecisionRecord, ExceptionCase
from engine.pipeline import run
from engine.registry import UnknownRuleset, registry
from engine.rules import InvalidInputs


class ApiError(Exception):
    def __init__(self, status: int, message: str, **extra):
        super().__init__(message)
        self.status = status
        self.payload = {"error": message, **extra}


class ApiView(View):
    def dispatch(self, request, *args, **kwargs):
        try:
            return super().dispatch(request, *args, **kwargs)
        except ApiError as exc:
            return JsonResponse(exc.payload, status=exc.status)

    def body(self, request) -> dict:
        try:
            data = json.loads(request.body or b"{}")
        except json.JSONDecodeError:
            raise ApiError(400, "body must be JSON") from None
        if not isinstance(data, dict):
            raise ApiError(400, "body must be a JSON object")
        return data


class HealthView(ApiView):
    def get(self, request):
        return JsonResponse({"status": "ok"})


class RulesetListView(ApiView):
    def get(self, request):
        return JsonResponse(
            {
                "rulesets": [
                    {
                        "name": name,
                        "default_version": registry.default_version(name),
                        "versions": [
                            registry.get(name, v).describe() for v in registry.versions(name)
                        ],
                    }
                    for name in registry.names()
                ]
            }
        )


class DecisionListView(ApiView):
    def post(self, request):
        data = self.body(request)
        for key in ("ruleset", "subject_reference", "inputs"):
            if key not in data:
                raise ApiError(400, f"{key} is required")
        try:
            result = run(
                data["ruleset"],
                str(data["subject_reference"]),
                data["inputs"],
                version=data.get("version"),
            )
        except UnknownRuleset as exc:
            raise ApiError(404, f"unknown ruleset {exc}") from None
        except InvalidInputs as exc:
            raise ApiError(400, "invalid inputs", details=exc.errors) from None
        return JsonResponse(
            {"created": result.created, "decision": presenters.record(result.record)},
            status=201 if result.created else 200,
        )


class DecisionDetailView(ApiView):
    def get(self, request, reference):
        try:
            rec = DecisionRecord.objects.by_reference(reference)
        except DecisionRecord.DoesNotExist:
            raise ApiError(404, "no such decision") from None
        return JsonResponse(presenters.record(rec))


class ExceptionListView(ApiView):
    def get(self, request):
        status = request.GET.get("status", ExceptionCase.Status.OPEN)
        cases = ExceptionCase.objects.select_related("record")
        if status != "all":
            cases = cases.filter(status=status)
        return JsonResponse({"exceptions": [presenters.case(c) for c in cases]})


class ExceptionDetailView(ApiView):
    def get(self, request, pk):
        try:
            exc = ExceptionCase.objects.select_related("record").get(pk=pk)
        except ExceptionCase.DoesNotExist:
            raise ApiError(404, "no such exception") from None
        return JsonResponse(presenters.case(exc, with_record=True))


class ExceptionResolveView(ApiView):
    def post(self, request, pk):
        data = self.body(request)
        try:
            exc = resolution.resolve(
                pk,
                action=data.get("action", ""),
                by=str(data.get("resolved_by", "")),
                note=str(data.get("note", "")),
                values=data.get("values"),
            )
        except ExceptionCase.DoesNotExist:
            raise ApiError(404, "no such exception") from None
        except resolution.AlreadyResolved:
            raise ApiError(409, "already resolved") from None
        except resolution.InvalidResolution as e:
            raise ApiError(400, str(e)) from None
        return JsonResponse(presenters.case(exc, with_record=True))


class MetricsView(ApiView):
    def get(self, request):
        since: datetime | None = None
        if raw := request.GET.get("since"):
            since = parse_datetime(raw)
            if since is None:
                raise ApiError(400, "since must be an ISO 8601 datetime")
        return JsonResponse(metrics.counts(ruleset_name=request.GET.get("ruleset"), since=since))
